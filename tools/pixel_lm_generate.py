#!/usr/bin/env python3
"""
Pixel-Token Language Model Generation Script

Samples continuations from a trained pixel LM and emits three projections:
- Pixel-strip PNG: one pixel per token
- Word-tile PNG: visual word tiles from wordbase
- Text: decoded word sequence

All three projections are driven by the SAME id sequence.
"""

import argparse
import sys
import os
from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np
import torch
from PIL import Image, ImageDraw

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pixel_tokenizer import PixelTokenizer, SpecialTokens
from tools.train_pixel_lm import PixelTransformer


class PixelLMGenerator:
    """
    Generator for pixel-token language model with multi-modal output.
    """

    def __init__(
        self,
        model_path: str,
        wordbase_path: Optional[Path] = None,
        device: str = "cpu",
    ):
        """
        Initialize generator with trained model.

        Args:
            model_path: Path to trained checkpoint (.pt)
            wordbase_path: Path to wordbase database
            device: Device to run on ('cpu' or 'cuda')
        """
        self.device = torch.device(device)

        # Load tokenizer
        self.tokenizer = PixelTokenizer(wordbase_path=wordbase_path)

        # Load model checkpoint
        print(f"Loading model from {model_path}...")
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)

        # Extract config
        config = checkpoint["config"]
        vocab_size = config["vocab_size"]
        d_model = config["d_model"]
        n_heads = config.get("n_heads", config.get("n_head", 8))  # Handle both naming conventions
        n_layers = config["n_layers"]
        d_ff = config["d_ff"]
        max_seq_len = config["max_seq_len"]
        dropout = config.get("dropout", 0.1)

        # Create model
        self.model = PixelTransformer(
            vocab_size=vocab_size,
            d_model=d_model,
            n_head=n_heads,  # Note: constructor uses n_head, not n_heads
            n_layers=n_layers,
            d_ff=d_ff,
            max_seq_len=max_seq_len,
            dropout=dropout,
        )

        # Load weights
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()

        print(f"Model loaded: {checkpoint.get('param_count', 'unknown')} parameters")
        print(f"Config: {config}")

    def close(self):
        """Clean up resources."""
        self.tokenizer.close()

    def encode_prompt(self, text: str) -> torch.Tensor:
        """
        Encode text prompt to token IDs.

        Args:
            text: Input text prompt

        Returns:
            Token IDs tensor [seq_len]
        """
        # Tokenize text
        token_ids = self.tokenizer.encode(text)

        # Validate token IDs are within vocab range
        max_id = self.model.vocab_size - 1
        validated_ids = []
        for tid in token_ids:
            if tid > max_id:
                # Replace out-of-vocab token with UNK
                validated_ids.append(SpecialTokens.UNK)
            else:
                validated_ids.append(tid)

        # Convert to tensor
        return torch.tensor(validated_ids, dtype=torch.long, device=self.device)

    @torch.no_grad()
    def sample_continuation(
        self,
        prompt_ids: torch.Tensor,
        max_new_tokens: int = 100,
        temperature: float = 1.0,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> List[int]:
        """
        Sample continuation from the model.

        Args:
            prompt_ids: Prompt token IDs [seq_len]
            max_new_tokens: Maximum new tokens to generate
            temperature: Sampling temperature (1.0 = default, lower = more deterministic)
            top_k: Top-k sampling (if set)
            top_p: Top-p (nucleus) sampling (if set)

        Returns:
            Complete token ID list (prompt + continuation)
        """
        # Start with prompt
        input_ids = prompt_ids.unsqueeze(0)  # [1, seq_len]

        generated_ids = input_ids.clone()

        for _ in range(max_new_tokens):
            # Forward pass
            logits = self.model(generated_ids)  # [1, seq_len, vocab_size]

            # Get logits for next token
            next_logits = logits[:, -1, :]  # [1, vocab_size]

            # Apply temperature
            next_logits = next_logits / temperature

            # Apply top-k sampling
            if top_k is not None:
                top_k = min(top_k, next_logits.size(-1))
                values, indices = torch.topk(next_logits, top_k, dim=-1)
                next_logits = torch.full_like(next_logits, float("-inf"))
                next_logits.scatter_(1, indices, values)

            # Apply top-p (nucleus) sampling
            if top_p is not None:
                sorted_logits, sorted_indices = torch.sort(next_logits, descending=True, dim=-1)
                cumulative_probs = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)

                # Remove tokens with cumulative probability above top_p
                sorted_indices_to_remove = cumulative_probs > top_p
                sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
                sorted_indices_to_remove[..., 0] = 0

                indices_to_remove = sorted_indices_to_remove.scatter(
                    1, sorted_indices, sorted_indices_to_remove
                )
                next_logits[indices_to_remove] = float("-inf")

            # Sample next token
            probs = torch.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)  # [1, 1]

            # Append to generated sequence
            generated_ids = torch.cat([generated_ids, next_token], dim=1)

            # Stop at EOS
            if next_token.item() == SpecialTokens.EOS:
                break

        return generated_ids.squeeze(0).tolist()  # [total_seq_len]

    def render_pixel_strip(self, token_ids: List[int]) -> np.ndarray:
        """
        Render token IDs as a pixel strip (one pixel per token).

        Args:
            token_ids: Token ID sequence

        Returns:
            RGB image array [seq_len, 1, 3]
        """
        seq_len = len(token_ids)
        pixels = np.zeros((seq_len, 1, 3), dtype=np.uint8)

        for i, token_id in enumerate(token_ids):
            if token_id >= SpecialTokens.NUM_SPECIAL:
                # Word token: id -> RGB pixel
                word_id = token_id - SpecialTokens.NUM_SPECIAL
                r = (word_id >> 16) & 0xFF
                g = (word_id >> 8) & 0xFF
                b = word_id & 0xFF
                pixels[i, 0] = [r, g, b]
            else:
                # Special token: gray scale
                special_color = 128 + token_id * 8
                pixels[i, 0] = [special_color, special_color, special_color]

        return pixels

    def render_word_tiles(self, token_ids: List[int], tile_width: int = 16) -> np.ndarray:
        """
        Render token IDs as word tiles from wordbase.

        Args:
            token_ids: Token ID sequence
            tile_width: Width of each tile in pixels

        Returns:
            RGB image array [tile_height, seq_len * tile_width, 3]
        """
        seq_len = len(token_ids)
        tiles = []

        for token_id in token_ids:
            if token_id >= SpecialTokens.NUM_SPECIAL:
                # Word token: look up wordbase entry
                word_id = token_id - SpecialTokens.NUM_SPECIAL

                # Query wordbase by id (direct SQL query)
                cursor = self.tokenizer.wordbase.conn.execute(
                    "SELECT word, id, color_hex FROM words WHERE id = ?",
                    (word_id,)
                )
                row = cursor.fetchone()

                if row:
                    word, word_db_id, color_hex = row
                    # Try to load voicebook tile
                    tile_path = Path("voicebook/tiles") / f"{word}_{word_db_id}.png"
                    if tile_path.exists():
                        tile_img = Image.open(tile_path).convert("RGB")
                        tile_img = tile_img.resize((tile_width, tile_width), Image.Resampling.NEAREST)
                        tiles.append(np.array(tile_img))
                        continue

                    # Fallback: colored square with semantic color
                    if not color_hex:
                        color_hex = "#888888"
                    r = int(color_hex[1:3], 16)
                    g = int(color_hex[3:5], 16)
                    b = int(color_hex[5:7], 16)
                    tile = np.full((tile_width, tile_width, 3), [r, g, b], dtype=np.uint8)
                    tiles.append(tile)
                else:
                    # Word not found: gray tile
                    tile = np.full((tile_width, tile_width, 3), [128, 128, 128], dtype=np.uint8)
                    tiles.append(tile)
            else:
                # Special token: gray tile
                special_color = 128 + token_id * 8
                tile = np.full(
                    (tile_width, tile_width, 3), [special_color, special_color, special_color], dtype=np.uint8
                )
                tiles.append(tile)

        # Concatenate tiles horizontally
        return np.hstack(tiles)

    def decode_text(self, token_ids: List[int]) -> str:
        """
        Decode token IDs to text.

        Args:
            token_ids: Token ID sequence

        Returns:
            Decoded text string
        """
        return self.tokenizer.decode(token_ids)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate continuations from pixel-token LM",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Input/output
    parser.add_argument(
        "--prompt",
        type=str,
        required=True,
        help="Text prompt to generate from",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="models/pixel_lm.pt",
        help="Path to trained model checkpoint",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="output/generation",
        help="Output file prefix (will create .png and .txt files)",
    )
    parser.add_argument(
        "--wordbase",
        type=str,
        default=None,
        help="Path to wordbase database (default: db/wordbase.db)",
    )

    # Generation parameters
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=100,
        help="Maximum new tokens to generate",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature (lower = more deterministic)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Top-k sampling (if set)",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=None,
        help="Top-p (nucleus) sampling (if set)",
    )

    # Rendering parameters
    parser.add_argument(
        "--tile-width",
        type=int,
        default=16,
        help="Width of each word tile in pixels",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device to run on",
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_prefix).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize generator
    generator = PixelLMGenerator(
        model_path=args.model,
        wordbase_path=Path(args.wordbase) if args.wordbase else None,
        device=args.device,
    )

    try:
        # Encode prompt
        print(f"\nPrompt: {args.prompt}")
        prompt_ids = generator.encode_prompt(args.prompt)
        print(f"Prompt tokens: {len(prompt_ids)}")

        # Sample continuation
        print(f"\nGenerating {args.max_new_tokens} tokens...")
        all_token_ids = generator.sample_continuation(
            prompt_ids=prompt_ids,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_k=args.top_k,
            top_p=args.top_p,
        )

        print(f"Total tokens: {len(all_token_ids)}")

        # Decode text
        text_output = generator.decode_text(all_token_ids)
        print(f"\nGenerated text:\n{text_output}")

        # Render pixel strip
        pixel_strip = generator.render_pixel_strip(all_token_ids)
        pixel_strip_path = f"{args.output_prefix}_pixel_strip.png"
        Image.fromarray(pixel_strip).save(pixel_strip_path)
        print(f"Pixel strip saved to: {pixel_strip_path}")

        # Render word tiles
        word_tiles = generator.render_word_tiles(all_token_ids, tile_width=args.tile_width)
        word_tiles_path = f"{args.output_prefix}_word_tiles.png"
        Image.fromarray(word_tiles).save(word_tiles_path)
        print(f"Word tiles saved to: {word_tiles_path}")

        # Save text
        text_path = f"{args.output_prefix}.txt"
        with open(text_path, "w") as f:
            f.write(text_output)
        print(f"Text saved to: {text_path}")

        print("\nGeneration complete!")
        print(f"All outputs use the same token ID sequence ({len(all_token_ids)} tokens)")

    finally:
        generator.close()


if __name__ == "__main__":
    main()