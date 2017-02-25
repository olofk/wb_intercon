module wb_intercon_tb;

   vlog_tb_utils vlog_tb_utils0();
   vlog_tap_generator #("wb_intercon.tap", 3) vtg();

   wb_mux_tb     #(.AUTORUN (0)) wb_mux_tb();
   wb_arbiter_tb #(.AUTORUN (0)) wb_arb_tb();
   wb_cdc_tb     #(.AUTORUN (0)) wb_cdc_tb();

   initial begin
      wb_mux_tb.run;
      vtg.ok("wb_mux: All tests passed!");
      wb_arb_tb.run;
      vtg.ok("wb_arbiter: All tests passed!");
      wb_cdc_tb.run;
      vtg.ok("wb_cdc: All tests passed!");

      #3 $finish;
   end

endmodule
