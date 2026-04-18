module or17_chain (
    input  wire [16:0] a,
    output wire        y
);

    wire [16:0] s;

    assign s[0]  = a[0];
    assign s[1]  = s[0]  | a[1];
    assign s[2]  = s[1]  | a[2];
    assign s[3]  = s[2]  | a[3];
    assign s[4]  = s[3]  | a[4];
    assign s[5]  = s[4]  | a[5];
    assign s[6]  = s[5]  | a[6];
    assign s[7]  = s[6]  | a[7];
    assign s[8]  = s[7]  | a[8];
    assign s[9]  = s[8]  | a[9];
    assign s[10] = s[9]  | a[10];
    assign s[11] = s[10] | a[11];
    assign s[12] = s[11] | a[12];
    assign s[13] = s[12] | a[13];
    assign s[14] = s[13] | a[14];
    assign s[15] = s[14] | a[15];
    assign s[16] = s[15] | a[16];

    assign y = s[16];

endmodule
