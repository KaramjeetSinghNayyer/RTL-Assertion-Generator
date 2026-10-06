`timescale 1ns/1ps
module abs_formal (
    input wire clock,
    input wire reset,
    input wire start_port,
    input wire [31:0] x
);
wire done_port;
wire [31:0] return_port;
\abs  dut (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .x(x), .return_port(return_port));
abs_acsl_sva acsl_checker (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .x(x), .return_port(return_port));
endmodule
