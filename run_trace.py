import sys
import argparse
from tools.boot_xv6_gpu import boot_xv6_on_gpu

# boot_xv6_on_gpu("boot_images/alpine_Image", trace_file="trace.jsonl", trace_max=500)
from tools.boot_xv6_gpu import boot_xv6_on_gpu, memory
import sys
# we need to hook into the middle of the function to print memory
