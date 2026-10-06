// Compile with the original RTL and corresponding checker.
bind \max  max_acsl_sva acsl_checker (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .a(a), .b(b), .return_port(return_port));
