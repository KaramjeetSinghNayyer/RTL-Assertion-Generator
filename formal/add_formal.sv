`timescale 1ns/1ps
module add_formal (
    input wire clock,
    input wire reset,
    input wire start_port,
    input wire [31:0] x,
    input wire [31:0] y
);
wire done_port;
wire [31:0] return_port;
add dut (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .x(x), .y(y), .return_port(return_port));
add_acsl_sva acsl_checker (.clock(clock), .reset(reset), .start_port(start_port), .done_port(done_port), .x(x), .y(y), .return_port(return_port));
endmodule
