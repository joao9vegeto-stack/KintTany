#!/usr/bin/env python3
import argparse
import os

from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen3-Coder Quick Start")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="write a quick sort algorithm.",
        help="Prompt enviado ao modelo.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("QWEN_MODEL", "Qwen/Qwen3-Coder-Next"),
        help="Modelo Hugging Face a carregar.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=2048,
        help="Máximo de tokens novos na resposta.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Valida imports/configuração sem baixar o modelo.",
    )
    args = parser.parse_args()

    if args.check:
        print(f"OK: transformers disponível; modelo configurado: {args.model}")
        return

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype="auto",
        device_map="auto",
    )

    messages = [{"role": "user", "content": args.prompt}]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=args.max_new_tokens,
    )
    generated_ids = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]

    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    print(response)


if __name__ == "__main__":
    main()
