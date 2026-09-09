#!/bin/bash
# Guest-side boot optimization script
# Run inside the VM after boot: sudo bash /host_zion/projects/visual_audio/optimize_boot.sh

set -e

echo "[*] Applying boot optimizations..."

# 1. Disable unnecessary services (faster boot)
echo "[+] Disabling unnecessary services..."
sudo systemctl disable --now bluetooth.service
sudo systemctl disable --now snapd.service snapd.socket
sudo systemctl disable --now cups.service cups-browsed.service
sudo systemctl disable --now whoopsie.service

# 2. Reduce systemd timeout (faster boot on slow devices)
echo "[+] Reducing systemd timeouts..."
sudo sed -i 's/^#DefaultTimeoutStartSec=.*/DefaultTimeoutStartSec=5s/' /etc/systemd/system.conf
sudo sed -i 's/^#DefaultTimeoutStopSec=.*/DefaultTimeoutStopSec=5s/' /etc/systemd/system.conf

# 3. Disable GDM animations (faster login)
echo "[+] Disabling GDM animations..."
sudo -u gdm dbus-launch gsettings set org.gnome.desktop.session idle-delay 0 || true
sudo sed -i '/^#WaylandEnable=false/a WaylandEnable=false' /etc/gdm3/custom.conf || true

# 4. Enable prelink (faster app startup)
echo "[+] Installing prelink..."
sudo apt-get update -qq
sudo apt-get install -y -qq prelink
sudo sed -i 's/^PRELINKING=.*/PRELINKING=yes/' /etc/default/prelink
sudo /etc/cron.daily/prelink 2>/dev/null || true

# 5. Optimize filesystem (faster access)
echo "[+] Optimizing filesystem..."
sudo e4defrag / 2>/dev/null || true

# 6. Reduce journal size (faster boot)
echo "[+] Reducing journal size..."
sudo journalctl --vacuum-size=50M
sudo sed -i 's/^SystemMaxUse=.*/SystemMaxUse=50M/' /etc/systemd/journald.conf

# 7. Enable parallel boot (systemd default, but verify)
echo "[+] Parallel boot is enabled by default in systemd"

echo ""
echo "[*] Boot optimizations applied!"
echo "[*] Reboot to see improvements: sudo reboot"
echo ""
echo "[*] To measure boot time: systemd-analyze"
echo "[*] To see slow services: systemd-analyze blame"