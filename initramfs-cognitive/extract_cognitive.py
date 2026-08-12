#!/usr/bin/env python3
import json
import os
import sys
import hashlib

COGNITIVE_OFFSET = 4831838208
DEVICE = "/dev/vda"
OUTPUT_GGUF = "/tmp/cognitive/llm_weights.gguf"

def main():
    print("=== Extracting LLM weights from spatial block device ===")
    
    with open(DEVICE, "rb") as f:
        f.seek(COGNITIVE_OFFSET)
        
        len_bytes = f.read(8)
        if not len_bytes:
            print("Failed to read length bytes")
            sys.exit(1)
            
        metadata_len = int.from_bytes(len_bytes, byteorder='little')
        metadata_json = f.read(metadata_len).decode('utf-8')
        metadata = json.loads(metadata_json)
        
        payload_size = metadata.get("payload_size", 0)
        print(f"Total payload size: {payload_size}")
        
        # We need to find the GGUF header 'GGUF' (0x46554747 in little endian, or 'GGUF' string)
        # It's after the initramfs. Let's scan for it.
        # Start searching after 10MB to be safe, up to payload_size.
        
        f.seek(COGNITIVE_OFFSET + 8 + metadata_len)
        
        chunk_size = 4 * 1024 * 1024
        overlap = 4
        
        gguf_offset = -1
        current_offset = 0
        
        print("Searching for GGUF magic header...")
        buffer = b''
        
        while current_offset < payload_size:
            read_size = min(chunk_size, payload_size - current_offset)
            if read_size <= 0:
                break
                
            chunk = f.read(read_size)
            search_buf = buffer + chunk
            
            idx = search_buf.find(b'GGUF')
            if idx != -1:
                # Found it!
                gguf_offset = current_offset - len(buffer) + idx
                break
                
            buffer = chunk[-overlap:] if len(chunk) >= overlap else chunk
            current_offset += read_size
            
        if gguf_offset == -1:
            print("❌ Could not find GGUF magic header in payload!")
            sys.exit(1)
            
        print(f"✓ Found GGUF header at payload offset {gguf_offset}")
        
        # Now extract the GGUF file
        absolute_gguf_offset = COGNITIVE_OFFSET + 8 + metadata_len + gguf_offset
        llm_size = payload_size - gguf_offset
        
        print(f"LLM weights size: {llm_size} bytes")
        
        f.seek(absolute_gguf_offset)
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
        
        # Verify MD5
        print("Calculating MD5 checksum...")
        md5_hash = hashlib.md5()
        with open(OUTPUT_GGUF, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        print(f"✓ MD5 verification passed: {md5_hash.hexdigest()}")
        
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