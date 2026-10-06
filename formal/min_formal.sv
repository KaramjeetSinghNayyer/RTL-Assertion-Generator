`timescale 1ns/1ps
module min_formal (
    input wire clock,
    input wire reset,
    input wire start_port,
    input wire [31:0] a,
    input wire [31:0] b
);
wire done_port;
wire [31:0] return_port;
\min  dut (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .a(a), .b(b), .return_port(return_port));
min_acsl_sva acsl_checker (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .a(a), .b(b), .return_port(return_port));
endmodule
