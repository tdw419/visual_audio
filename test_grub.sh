#!/bin/bash
virt-customize -a test-cloudimg.raw --run-command 'grub-install /dev/sda && update-grub'
