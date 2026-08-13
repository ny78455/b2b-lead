from transformers import AutoTokenizer, AutoModelForCausalLM
import logging

logging.basicConfig(level=logging.INFO)
MODEL_ID = "google/gemma-4-E2B-it"

def test():
    logging.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    logging.info("Loading model...")
    # Just load on CPU for quick test if no CUDA
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        device_map="auto"
    )
    
    messages = [
        {"role": "user", "content": "Write a short joke on climate."}
    ]
    inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_dict=True, return_tensors="pt")
    inputs = inputs.to(model.device)
    
    logging.info("Generating...")
    outputs = model.generate(**inputs, max_new_tokens=50)
    input_len = inputs["input_ids"].shape[-1]
    response = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True)
    logging.info(f"Response: {response}")

if __name__ == "__main__":
    test()
