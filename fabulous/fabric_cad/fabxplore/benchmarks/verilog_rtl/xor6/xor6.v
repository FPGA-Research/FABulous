module xor6 (
    input [5:0] data,
    output out
);
    assign out = ^data;
endmodule
