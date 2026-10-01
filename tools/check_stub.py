with open("ubuntu_vmlinuz", "rb") as f:
    data = f.read()

# Let's search for "EFI handover" strings or just verify
