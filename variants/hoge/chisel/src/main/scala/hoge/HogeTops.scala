package hoge

import chisel3.stage.ChiselStage

object HogeTops extends App {
  private val stage = new ChiselStage
  private val targetDir = Array("--target-dir", ".")

  stage.emitVerilog(new streaming.INTTWrap(streaming.Config()), targetDir)
  stage.emitVerilog(new streaming.NTTWrap(streaming.Config()), targetDir)
  stage.emitVerilog(new nttid.NTTidPackedTop(nttid.Config()), targetDir)
  stage.emitVerilog(new externalproduct.ExternalProductWrap()(externalproduct.Config()), targetDir)
}
