// Compile with the original RTL and corresponding checker.
bind add add_acsl_sva acsl_checker (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .x(x), .y(y), .return_port(return_port));
