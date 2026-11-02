# tools/gdb_segv_capture.gdb — non-interactive GDB command file for DEFECT-22 live SIGSEGV capture.
# Intercepts SIGSEGV before Python's faulthandler destroys siginfo/ucontext.
set pagination off
set confirm off
set debuginfod enabled off
set print frame-arguments none
handle SIGSEGV stop print nopass
run

# Capture block: emit greppable machine-readable markers and context
printf "DEFECT22_CAPTURE_START\n"
if $_thread != 0
  printf "DEFECT22_CAPTURE: segv_caught=true\n"
  printf "DEFECT22_CAPTURE: signal=SIGSEGV\n"
  printf "DEFECT22_CAPTURE: pc="
  p/x $pc
  printf "DEFECT22_CAPTURE: si_addr="
  p $_siginfo._sifields._sigfault.si_addr
  printf "DEFECT22_CAPTURE: fault_instruction=\n"
  x/2i $pc
  printf "DEFECT22_CAPTURE: pc_symbol="
  info symbol $pc
  printf "DEFECT22_CAPTURE: exitcode="
  p $_exitcode
  printf "DEFECT22_CAPTURE: bt_start\n"
  thread apply all bt 40
  printf "DEFECT22_CAPTURE: bt_end\n"
else
  printf "DEFECT22_CAPTURE: segv_caught=false\n"
  printf "DEFECT22_CAPTURE: signal=none\n"
  printf "DEFECT22_CAPTURE: pc=none\n"
  printf "DEFECT22_CAPTURE: si_addr=none\n"
  printf "DEFECT22_CAPTURE: fault_instruction=none\n"
  printf "DEFECT22_CAPTURE: pc_symbol=none\n"
  printf "DEFECT22_CAPTURE: exitcode="
  p $_exitcode
end
printf "DEFECT22_CAPTURE_END\n"
quit
