"""Qwen2.5-1.5B-Instruct LoRA 微调，并导出合并后的 HF 权重。

用法：
python train/lora_sft.py --base D:/jiami/models/Qwen2.5-1.5B-Instruct --out D:/jiami/models/qwen2.5-1.5b-lora

数据来自 train/prepare_sft.py 生成的对话 JSONL；只对 assistant 段计算 loss。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, set_seed

ROOT = Path(__file__).resolve().parent.parent
MAX_LENGTH = 2048


class PadCollator:
    def __init__(self, pad_token_id: int):
        self.pad_token_id = pad_token_id

    def __call__(self, features: list[dict]) -> dict:
        width = max(len(item["input_ids"]) for item in features)
        input_ids, attention, labels = [], [], []
        for item in features:
            pad = width - len(item["input_ids"])
            input_ids.append(item["input_ids"] + [self.pad_token_id] * pad)
            attention.append(item["attention_mask"] + [0] * pad)
            labels.append(item["labels"] + [-100] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def build_dataset(path: Path, tokenizer, max_length: int):
    dataset = load_dataset("json", data_files=str(path), split="train")

    def encode(example):
        messages = example["messages"]
        full_text = tokenizer.apply_chat_template(messages, tokenize=False)
        prompt_text = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
        full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"][:max_length]
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        if full_ids[: len(prompt_ids)] != prompt_ids:
            raise ValueError("prompt 不是完整对话的前缀，无法正确屏蔽 loss")
        prompt_len = min(len(prompt_ids), len(full_ids))
        labels = [-100] * prompt_len + full_ids[prompt_len:]
        return {
            "input_ids": full_ids,
            "attention_mask": [1] * len(full_ids),
            "labels": labels,
        }

    return dataset.map(encode, remove_columns=dataset.column_names, desc="tokenizing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path(r"D:\jiami\models\Qwen2.5-1.5B-Instruct"))
    parser.add_argument("--train", type=Path, default=ROOT / "data" / "train_messages.jsonl")
    parser.add_argument("--valid", type=Path, default=ROOT / "data" / "valid_messages.jsonl")
    parser.add_argument("--out", type=Path, default=Path(r"D:\jiami\models\qwen2.5-1.5b-lora"))
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--accum", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH)
    parser.add_argument("--limit", type=int, default=0, help="只用前 N 条训练样本，冒烟测试用")
    parser.add_argument("--max-steps", type=int, default=-1, help="覆盖 epoch 数，冒烟测试用")
    parser.add_argument("--skip-merge", action="store_true", help="只保存 adapter，不合并权重，冒烟测试用")
    args = parser.parse_args()

    set_seed(42)
    if not torch.cuda.is_available():
        raise SystemExit("CUDA 不可用，LoRA 训练需要 GPU")

    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_set = build_dataset(args.train, tokenizer, args.max_length)
    if args.limit:
        train_set = train_set.select(range(min(args.limit, len(train_set))))
    eval_set = build_dataset(args.valid, tokenizer, args.max_length) if args.valid.exists() else None
    lengths = [len(row["input_ids"]) for row in train_set]
    print(f"train={len(train_set)} eval={len(eval_set) if eval_set else 0} "
          f"tokens min/avg/max={min(lengths)}/{sum(lengths)//len(lengths)}/{max(lengths)}")

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=dtype, trust_remote_code=True)
    model.config.use_cache = False
    model.to("cuda")
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()

    lora = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    args.out.mkdir(parents=True, exist_ok=True)
    training = TrainingArguments(
        output_dir=str(args.out / "checkpoints"),
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.accum,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        eval_strategy="epoch" if eval_set else "no",
        save_strategy="no",
        bf16=dtype == torch.bfloat16,
        fp16=dtype == torch.float16,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="adamw_torch",
        report_to="none",
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        remove_unused_columns=False,
        seed=42,
    )
    trainer = Trainer(
        model=model,
        args=training,
        train_dataset=train_set,
        eval_dataset=eval_set,
        data_collator=PadCollator(tokenizer.pad_token_id),
        processing_class=tokenizer,
    )
    trainer.train()

    adapter_dir = args.out / "adapter"
    trainer.model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    print(f"adapter 已保存: {adapter_dir}")

    merged_dir = args.out / "merged"
    if args.skip_merge:
        print("已跳过合并（--skip-merge）")
    else:
        del trainer
        torch.cuda.empty_cache()
        model = model.to("cpu")
        merged = model.merge_and_unload()
        merged.save_pretrained(merged_dir, safe_serialization=True)
        tokenizer.save_pretrained(merged_dir)
        print(f"合并权重已保存: {merged_dir}")

    summary = {
        "base": str(args.base),
        "adapter": str(adapter_dir),
        "merged": str(merged_dir),
        "train": len(train_set),
        "eval": len(eval_set) if eval_set else 0,
        "epochs": args.epochs,
        "max_steps": args.max_steps,
        "lr": args.lr,
        "dtype": str(dtype),
    }
    (args.out / "train_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
