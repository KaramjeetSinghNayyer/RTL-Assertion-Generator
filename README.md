# RTL-Assertion-Generator
Created to comply with the completion of course project of C-based VLSI 

//Nameet 6/10/26 11:26 am:
Performed Phase 1 of checking 3 C's for the C files and obtaining HLS metadata.

Next step is to find metadata, for the Bambu tool:

1. to find Port and Signal Mappings: 
The interface metadata is written at the very top of abs.v, add.v, max.v, and min.v. If you open add.v, you will see the Verilog module declaration listing the exact names Bambu chose for the clock, reset, start, done, and data signals.   

2. to Find Timing and Latency: The latency and clock timing metadata is located in the Synopsys Design Constraints (.sdc) files, such as abs.sdc and max.sdc, which are located inside the vivado_flow output folders.   