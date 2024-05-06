module bitbang (s_clk, s_data, strobe, data, active, clk, resetn);
	localparam on_pattern = 16'hFAB1; 
	localparam off_pattern = 16'hFAB0; 
	input s_clk;
	input s_data;
	output reg strobe;
	output reg [31:0] data;
	output reg active;
	input clk; 
	input resetn;

	reg [3:0] s_data_sample;
	reg [3:0] s_clk_sample;

	reg [31:0] serial_data;
	reg [15:0] serial_control;

	reg local_strobe;
	reg old_local_strobe;

	always @ (posedge clk, negedge resetn)
	begin : p_input_sync
		if (!resetn) begin
			s_data_sample <= 4'b0;
			s_clk_sample <= 4'b0;
		end else begin
			s_data_sample <= {s_data_sample[3-1:0],s_data};
			s_clk_sample  <= {s_clk_sample[3-1:0],s_clk};
		end
	end

	always @ (posedge clk, negedge resetn)
	begin : p_in_shift
		if (!resetn) begin
			serial_data <= 32'b0;
			serial_control <= 16'b0;
		end else begin
			// on s_clk_sample rising edge, we sample in a serial_data bit
			if ((s_clk_sample[3] == 1'b0) && (s_clk_sample[3-1] == 1'b1)) begin
				serial_data <= {serial_data[31-1:0],s_data_sample[3]};
			end
			// on s_clk_sample faling edge, we sample in a serial_data bit
			if ((s_clk_sample[3] == 1'b1) && (s_clk_sample[3-1] == 1'b0)) begin
				serial_control <= {serial_control[15-1:0],s_data_sample[3]}; // its data again, but its sampled on the other edge
			end
		end
	end

// we could replicate the following 
	always @ (posedge clk, negedge resetn)
	begin : p_parallel_load
		if (!resetn) begin
			local_strobe <= 1'b0;
			data <= 32'b0;
			old_local_strobe <= 1'b0;
			strobe <= 1'b0;
		end else begin
			local_strobe <= 1'b0; // will be overwritten if next conditional is true
			if (serial_control == on_pattern) begin// x"FAB1" then      
				data <= serial_data;
				local_strobe <= 1'b1;
			end //else begin
			//	data <= data;
			//	local_strobe <= 1'b0;
			// end
			old_local_strobe <= local_strobe;
			strobe <= local_strobe & ~old_local_strobe; // activates strobe for one clock cycle after "FAB0" was detected
		end
	end

// we could replicate the following 
	always @ (posedge clk, negedge resetn)
	begin : active_FSM
		if (!resetn) begin
			active <= 1'b0;
		end else begin
			if (serial_control == on_pattern) begin// x"FAB1" then      
				active <= 1'b1;
			end
			if (serial_control == off_pattern) begin// x"FAB0" then      
				active <= 1'b0;
			end
		end
	end

// the following is just copy and past, in case we want use the bitbang interface to shift in other data (let's say to drive CPU port)
// we can also read back the data by loading the parallel shift and shifting the content to an output pin
//p_parallel_load2: process(clk)
//begin
//    if clk'event and clk=1'b1 then
//        local_strobe <= 1'b0;       // will be overwritten if next conditional is true
//        if serial_control = x"FAB1" then      
//            data2 <= serial_data;  
//            local_strobe2 <= 1'b1;
//            old_local_strobe2 <= local_strobe;
//        end if;
//      strobe2 <= local_strobe2 and (not old_local_strobe2)   // activates strobe for one clock cycle after "FAB0" was detected
//    end if;
//end process;

endmodule