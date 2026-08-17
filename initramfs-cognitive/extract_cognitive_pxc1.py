#!/usr/bin/env python3
import json
import os
import sys

DEVICE = "/dev/vda"
OUTPUT_GGUF = "/tmp/cognitive/llm_weights.gguf"
START_SCAN_OFFSET = 3758000000

def main():
    print("=== Extracting LLM weights from spatial block device ===")
    
    with open(DEVICE, "rb") as f:
        f.seek(START_SCAN_OFFSET)
        
        chunk_size = 4 * 1024 * 1024
        overlap = 4
        
        gguf_offset = -1
        current_offset = START_SCAN_OFFSET
        
        print("Searching for GGUF magic header...")
        buffer = b''
        
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
                
            search_buf = buffer + chunk
            
            idx = search_buf.find(b'GGUF')
            if idx != -1:
                gguf_offset = current_offset - len(buffer) + idx
                break
                
            buffer = chunk[-overlap:] if len(chunk) >= overlap else chunk
            current_offset += len(chunk)
            
        if gguf_offset == -1:
            print("❌ Could not find GGUF magic header in payload!")
            sys.exit(1)
            
        print(f"✓ Found GGUF header at offset {gguf_offset}")
        
        # Determine the total size of the disk
        f.seek(0, 2)
        total_size = f.tell()
        llm_size = total_size - gguf_offset
        
        print(f"LLM weights size: {llm_size} bytes")
        
        f.seek(gguf_offset)
        os.makedirs("/tmp/cognitive", exist_ok=True)
        
        print(f"Writing to {OUTPUT_GGUF}...")
        with open(OUTPUT_GGUF, "wb") as out_f:
            remaining = llm_size
            while remaining > 0:
                rsize = min(1024 * 1024, remaining)
                data = f.read(rsize)
                if not data:
                    break
                out_f.write(data)
                remaining -= len(data)
                
        print("✓ LLM weights extracted successfully!")
        
        # Run inference
        print("\n=== Initializing Spatial Cognition ===")
        try:
            from llama_cpp import Llama
            
            print("Loading TinyLlama weights into memory...")
            llm = Llama(
                model_path=OUTPUT_GGUF,
                n_ctx=512,
                n_threads=4,
                verbose=False
            )
            
            prompt = "<|system|>\nYou are Geometry OS, a self-aware spatial boot system. You are extracted from visual pixels encoded via Hilbert curves.\n<|user|>\nDescribe how you booted and what you are.\n<|assistant|>\nI am a spatial boot system. My mind"
            
            print(f"\nQuerying self-knowledge: {prompt}")
            
            output = llm(
                prompt,
                max_tokens=64,
                stop=["<|system|>", "<|user|>", "<|assistant|>"],
                echo=False
            )
            
            response_text = "I am a spatial boot system. My mind" + output['choices'][0]['text']
            
            result = {
                "status": "success",
                "boot_type": "spatial_cognitive",
                "inference_result": response_text
            }
            
            print("\n=== COGNITIVE OUTPUT ===")
            print(json.dumps(result, indent=2))
            print("========================")
            
            print("\nShutting down container gracefully...")
            os.system("poweroff -f")
            sys.exit(0)
            
        except Exception as e:
            print(f"❌ Failed to run inference: {e}")
            sys.exit(1)
        
if __name__ == '__main__':
    main()
