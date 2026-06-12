import chisel3._

class YataRainttTop(implicit val conf: Config) extends Module {
  val io = IO(new Bundle {
    val intt_in = Input(Vec(conf.nttsize, UInt(conf.Qbit.W)))
    val intt_validin = Input(Bool())
    val intt_out = Output(Vec(conf.nttsize, SInt(conf.wordbits.W)))
    val intt_validout = Output(Bool())

    val ntt_in = Input(Vec(conf.nttsize, SInt(conf.wordbits.W)))
    val ntt_validin = Input(Bool())
    val ntt_out = Output(Vec(conf.nttsize, UInt(conf.Qbit.W)))
    val ntt_validout = Output(Bool())
  })

  private val intt = Module(new INTT)
  intt.io.in := io.intt_in
  intt.io.validin := io.intt_validin
  io.intt_out := intt.io.out
  io.intt_validout := intt.io.validout

  private val ntt = Module(new NTT)
  ntt.io.in := io.ntt_in
  ntt.io.validin := io.ntt_validin
  io.ntt_out := ntt.io.out
  io.ntt_validout := ntt.io.validout
}

object YataRainttTop extends App {
  (new chisel3.stage.ChiselStage).emitVerilog(
    new YataRainttTop()(Config()),
    Array(
      "--target-dir",
      ".",
      "--emission-options=disableMemRandomization,disableRegisterRandomization"
    )
  )
}
