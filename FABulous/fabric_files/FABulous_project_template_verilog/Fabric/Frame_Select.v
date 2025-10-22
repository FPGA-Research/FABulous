module Frame_Select #(
    parameter integer MaxFramesPerCol = 20,
    parameter integer FrameSelectWidth = 5,
    parameter reg [FrameSelectWidth-1:0] Col = 18
) (
    input [MaxFramesPerCol-1:0] FrameStrobe_I,
    output reg [MaxFramesPerCol-1:0] FrameStrobe_O,
    input [FrameSelectWidth-1:0] FrameSelect,
    input FrameStrobe
);

    //FrameStrobe_O = 0;
    always @(*) begin
        if (FrameStrobe && (FrameSelect == Col)) FrameStrobe_O = FrameStrobe_I;
        else FrameStrobe_O = 'd0;
    end

endmodule
