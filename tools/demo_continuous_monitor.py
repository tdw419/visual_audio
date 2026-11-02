#!/usr/bin/env python3
"""
demo_continuous_monitor.py — Demo of continuous framebuffer monitoring.

Shows how to use the ContinuousScreenMonitor for:
1. Watching boot progress
2. Detecting login prompts
3. Monitoring daemon output
"""

import sys
import time

sys.path.insert(0, 'tools')

from glyph_screen_reader_continuous import ContinuousScreenMonitor


def demo_boot_prompt_watcher():
    """Example: Watch for login prompt during boot."""
    print("=" * 70)
    print("DEMO 1: Boot Prompt Watcher")
    print("=" * 70)

    monitor = ContinuousScreenMonitor(
        char_width=8,
        char_height=16,
        tolerance=0.0,
        use_vga_font=True
    )

    # Monitor test PNG (simulating framebuffer)
    print("\nMonitoring for 'login:' prompt in test image...")
    print("(In production, use --device /dev/fb0 for real framebuffer)\n")

    # Watch for boot prompts
    watch_phrases = ['login:', 'shell', 'root@', '# ', '$ ']

    try:
        monitor.monitor_png(
            'test_login_prompt.png',
            interval=0.1,
            watch_phrases=watch_phrases,
            verbose=True
        )
    except KeyboardInterrupt:
        print("\nDemo stopped")


def demo_programmatic_api():
    """Example: Using the monitor programmatically."""
    print("\n" + "=" * 70)
    print("DEMO 2: Programmatic API Usage")
    print("=" * 70)

    # Create monitor
    monitor = ContinuousScreenMonitor(
        char_width=8,
        char_height=16,
        tolerance=0.0,
        use_vga_font=True
    )

    # Watch for specific phrases
    monitor.watch_phrases = {'error', 'warning', 'failed', 'login:'}

    print("\nMonitoring test image...")
    print(f"Watching for: {', '.join(monitor.watch_phrases)}")

    # Read once (in production, use polling loop)
    decoded = monitor._decode_source('test_login_prompt.png', is_png=True)

    print(f"\nDecoded text:")
    print(decoded.text)
    print(f"\nFound watch phrases: {monitor._check_watch_phrases(decoded)}")

    # You can also integrate with AI:
    if 'login' in decoded.text.lower():
        print("\n🤖 AI: Login prompt detected - boot complete")
        print("   Next action: Send credentials or report success")


def demo_ai_integration_example():
    """Example: How AI would use this for boot verification."""
    print("\n" + "=" * 70)
    print("DEMO 3: AI Integration Pattern")
    print("=" * 70)

    print("""
For AI agents, use this pattern:

1. Initialize monitor once:
   monitor = ContinuousScreenMonitor(use_vga_font=True)

2. Poll for changes:
   while True:
       decoded = monitor._read_framebuffer_decode('/dev/fb0')

       if monitor._detect_changes(decoded.text):
           # Send to AI for interpretation
           ai_result = your_ai_analyze_function(decoded.text)

           if ai_result.is_boot_complete:
               break

       time.sleep(0.1)

3. Or watch for specific triggers:
   monitor.watch_phrases = {'login:', 'error', 'panic'}

   # Check if triggers fired
   found = monitor._check_watch_phrases(decoded)
   if 'error' in found:
       # Boot failed
       take_recovery_action()
""")


def demo_cli_usage():
    """Example: Command-line usage."""
    print("\n" + "=" * 70)
    print("DEMO 4: Command-Line Usage")
    print("=" * 70)

    print("""
# Monitor real framebuffer (needs sudo)
sudo python3 tools/glyph_screen_reader_continuous.py \\
    --device /dev/fb0 \\
    --watch 'login:' \\
    --interval 0.1

# Monitor PNG file (for testing)
python3 tools/glyph_screen_reader_continuous.py \\
    --png test_login_prompt.png \\
    --watch 'login:' \\
    --watch 'root@' \\
    --interval 1.0

# Monitor with tolerance (for noisy displays)
python3 tools/glyph_screen_reader_continuous.py \\
    --device /dev/fb0 \\
    --tolerance 0.05 \\
    --interval 0.2
""")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("CONTINUOUS FRAMEBUFFER MONITORING — DEMOS")
    print("=" * 70)

    # Demo 1: Boot prompt watcher
    # demo_boot_prompt_watcher()  # Skipped to avoid blocking

    # Demo 2: Programmatic API
    demo_programmatic_api()

    # Demo 3: AI integration pattern
    demo_ai_integration_example()

    # Demo 4: CLI usage
    demo_cli_usage()

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)


if __name__ == '__main__':
    main()