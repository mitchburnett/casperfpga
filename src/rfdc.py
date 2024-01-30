import logging
import katcp
import os
import random

LOGGER = logging.getLogger(__name__)

class RFDC(object):
  """
  Casperfpga class encapsulating the rfdc Yellow Block
  """

  LMK = 'lmk'
  LMX = 'lmx'

  ADC0_OFFSET = 0x14000
  ADC1_OFFSET = 0x18000
  ADC2_OFFSET = 0x1c000
  ADC3_OFFSET = 0x20000

  # Common control and status registers
  VER_OFFSET = 0x0
  COMMON_MASTER_RST = 0x4
  COMMON_IRQ_STATUS = 0x100

  # Tile control and status registers
  RST_PO_STATE_MACHINE = 0x4
  RST_STATE_REG = 0x8
  CUR_STATE_REG = 0xc
  CLK_DETECT_REG = 0x84 #gen3 parts
  RST_COUNT_REG = 0x38
  IRQ_STAT_REG = 0x200
  IRQ_EN_REG = 0x204
  SLICE0_IRQ_REG = 0x208
  SLICE0_IRQ_EN = 0x20c
  SLICE1_IRQ_REG = 0x210
  SLICE1_IRQ_EN = 0x214
  #slice 2/3 registers for quad tile ADC tiles only
  SLICE2_IRQ_REG = 0x218
  SLICE2_IRQ_EN  = 0x21c
  SLICE3_IRQ_REG = 0x220
  SLICE3_IRQ_EN  = 0x224
  COMMON_STATUS_REG = 0x228
  TILE_DISABLE_REG = 0x230

  # converter types
  ADC_TILE = 0
  DAC_TILE = 1

  # nyquist zones
  NYQUIST_ZONE1 = 1
  NYQUIST_ZONE2 = 2

  # converter data types
  DTYPE_REAL = 0
  DTYPE_CMPLX = 1

  # PLL clock source
  CLK_SRC_EXTERNAL = 0
  CLK_SRC_INTERNAL = 1

  PLL_UNLOCKED = 1
  PLL_LOCKED = 2

  # background calibration blocks
  CAL_MODE1 = 1
  CAL_MODE2 = 2

  CAL_BLOCK_OCB1 = 0
  CAL_BLOCK_OCB2 = 1
  CAL_BLOCK_GCB  = 2
  CAL_BLOCK_TSCB = 3

  CAL_UNFREEZE = 0
  CAL_FREEZE = 1

  # trigger event
  EVENT_MIXER =  1
  EVENT_COARSE_DLY = 2
  EVENT_QMC = 4

  # QMC and Coarse Delay event update source
  EVNT_SRC_IMMEDIAT = 0 # Update after register writeE
  EVNT_SRC_SLICE = 1    # Update using SLICE
  EVNT_SRC_TILE = 2     # Update using TILE
  EVNT_SRC_SYSREF = 3   # Update using SYSREF
  EVNT_SRC_MARKER = 4   # update using MARKER
  EVNT_SRC_PL = 5       # update using PL event

  # inverse sinc fir modes
  INVSINC_FIR_DISABLED = 0 # disabled
  INVSINC_FIR_NYQUIST1 = 1 # first nyquist
  INVSINC_FIR_NYQUIST2 = 2 # second nyquist

  # image rection filter
  IMR_LOWPASS = 0
  IMR_HIGHPASS = 1

  class tile(object):
    pass

  class adc_slice(object):
    pass

  @classmethod
  def from_device_info(cls, parent, device_name, device_info, initialise=False, **kwargs):
    """
    Process device info and the memory map to populate necessary class info
    and return a RFDC instance.

    :param parent: The parent device, normally a casperfpga instance
    :param device_name:
    :param device_info:
    :param initialise:
    :param kwargs:
    :return:
    """
    return cls(parent, device_name, device_info, initialise, **kwargs)


  def __init__(self, parent, device_name, device_info, initialise=False):
    self.parent = parent
    self.logger = parent.logger
    self.name   = device_name
    self.device_info = device_info
    #self.clkfiles = []

    """
    apply the dtbo for the rfdc driver

    ideally, this would be incorporated as part of an extended `fpg` implementation that includes the device tree overlwy by including the
    dtbo as part of the programming process. The rfdc is the only block that is using the dto at the moment, so instead of completely
    implement this extended fpg functionality the rfdc instead manages its own application of the dto.
    """

    """
    Run only when a new client connects and the fpga is already running a design and want to create `casperfpga` `rfdc` helper container
    object from `get_system_information()`

    The `initialise` parameter is passed in here coming from the top-level casperfpga function `upload_to_ram_and_program`. That seems
    like it was intended for something simliar on skarab. However, that defaults to False for some reason when it seems more intuitive
    that default behavior should be True at program. But, I suppose there are any number of reasons that could makes more sense to default
    `False` (e.g., initializations like onboard PLLs are only done on power up, and are not necessarily initialized each time the fpga is
    programmed). As we always want the rfdc initialized on programming and the goal here is to support rfdc initialization when a new
    client connects and the fpga is already programmed (and potentially applying the dto in the rfdc object only temporary until further
    support is considered wen programming the fpg) we instead know that `upload_to_ram_and_program()` sets `prog_info` just before exit we
    need this anyway to know what `.dtbo` to apply so we just check if we know of something that has been programmed and use that.

    using `initialise` could make more sense in the context of knowing that the rfpll's need to be programmed and want to start those up
    when initializing the `rfdc` `casperfpga` object. But in that case we would still want to not apply the dto every time and now would
    require initializing different components. Instead, it would make more sense for the user to implement in their script the logic
    required to either initialize supporting rfdc components or not.
    """
    fpgpath = parent.transport.prog_info['last_programmed']
    if fpgpath != '':
    #if initialise:
      #fpgpath = parent.transport.prog_info['last_programmed']
      fpgpath, fpg = os.path.split(fpgpath)
      dtbo = os.path.join(fpgpath, "{}.dtbo".format(fpg.split('.')[0]))

      os.path.getsize(dtbo) # check if exists
      self.apply_dto(dtbo)


  def init(self, lmk_file=None, lmx_file=None, upload=False):
    """
    Initialize the rfdc driver, optionally program rfplls if file parameters are present.

    :param lmk_file: lmk tics hexdump (.txt) register file name
    :type lmk_file: str, optional

    :param lmx_file: lmx tics hexdump (.txt) register file name
    :type lmx_file: str, optional

    :param upload: Inidicate that the configuration files are local to the client and
        should be uploaded to the remote, will overwrite if exists on remote filesystem
    :type upload: bool, optional

    :return: `True` if completed successfully, `False` otherwise
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """

    if lmk_file:
      self.progpll('lmk', lmk_file, upload=upload)

    if lmx_file:
      self.progpll('lmx', lmx_file, upload=upload)

    t = self.parent.transport
    reply, informs = t.katcprequest(name='rfdc-init', request_timeout=t._timeout)

    return True


  def apply_dto(self, dtbofile):
    """

    """
    t = self.parent.transport

    os.path.getsize(dtbofile)
    port = random.randint(2000, 2500)

    # hacky tmp file to match tbs expected file format
    tbs_dtbo_name = 'tcpborphserver.dtbo'
    fd = open(dtbofile, 'rb')
    fdtbs_dtbo = open(tbs_dtbo_name, 'wb')
    for b in fd:
      fdtbs_dtbo.write(b)
    fdtbs_dtbo.close()
    fd.close()

    t.upload_to_flash(tbs_dtbo_name, force_upload=True)
    os.remove(tbs_dtbo_name)

    args = ("apply",)
    reply, informs = t.katcprequest(name='dto', request_timeout=t._timeout, request_args=args)

    if informs[0].arguments[0].decode() == 'applied\n':
      return True
    else:
      return False


  def show_clk_files(self):
    """
    Show a list of available remote clock register files to use for rfpll clock programming.

    :return: A list of available clock register files.
    :rtype: list

    :raises KatcpRequestFail: If KatcpTransport encounters an error.
    """
    t = self.parent.transport
    files = t.listbof()

    clkfiles = []
    for f in files:
      s = f.split('.')
      if len(s) > 1:
        if s[-1] == 'txt':
          clkfiles.append(f)
          #self.clkfiles.append(f)
    return clkfiles


  def del_clk_file(self, clkfname):
    """
    Remove an rfpll configuration clock file from the remote filesystem.

    :param clkfname: Name of clock configuration on remote filesystem.
    :type clkfname: str

    :return: `True` if file removed successfully, `False` otherwise.
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error.
    """
    t = self.parent.transport
    args = (clkfname, )
    reply, informs = t.katcprequest(name='delbof', request_timeout=t._timeout, request_args=args)
    return True


  def upload_clk_file(self, fpath, port=None, force_upload=False):
    """
    Upload a TICS hex dump (.txt) register file to the fpga for programming

    :param fpath: Path to a TICS register configuration file.
    :type fpath: str
    :param port: Port to use for upload, default to `None` using a random port.
    :type port: int, optional
    :param force_upload: Force to upload the file at `fpath`.
    :type force_upload: bool, optional

    :return: `True` if `fpath` is uploaded successfuly or already exists on
        remote filesystem. `False` otherwise.
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error.
    """
    t = self.parent.transport

    os.path.getsize(fpath)
    fname = os.path.basename(fpath)

    if not force_upload:
      clkfiles = self.show_clk_files()
      if clkfiles.count(fname) == 1:
        print("file exists on remote filesystem, not uploading. Use `force_upload=True` to overwrite.")
        return True

    if not port:
      port = random.randint(2000, 2500)

    t.upload_to_flash(fpath , port=port, force_upload=force_upload)

    return True


  def progpll(self, plltype, fpath=None, upload=False, port=None):
    """
    Program target RFPLL named by `plltype` with tics hexdump (.txt) register file named by
    `fpath`. Optionally upload the register file to the remote.

    :param plltype: Options are 'lmk' or 'lmx'
    :type client: str

    :param fpath: Local path to a tics hexdump register file, or the name of an
        available remote tics register file, default is that tcpboprphserver will look
        for a file called `rfpll.txt`.
    :type fpath: str, optional

    :param upload: Inidicate that the configuration file is local to the client and
        should be uploaded to the remote, this will overwrite any clock file on the remote
        by the same name.
    :type upload: bool, optional

    :param port: Port number to use for upload, default is `None` and will use a random port.
    :type port: int, optional

    :return: `True` if completes successfuly, `False` otherwise.
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error.
    """
    t = self.parent.transport

    plltype = plltype.lower()
    if plltype not in [self.LMK, self.LMX]:
      print('not a valid pll type')
      return False

    if fpath:
      if upload:
        os.path.getsize(fpath)
        self.upload_clk_file(fpath, force_upload=True)

      fname = os.path.basename(fpath)
      args = (plltype, fname)
    else:
      args = (plltype,)

    reply, informs = t.katcprequest(name='rfdc-progpll', request_timeout=t._timeout, request_args=args)

    return True


  def status(self):
    """
    Get RFDC ADC/DAC tile status. If tile is enabled, the tile state machine current state 
    and internal PLL lock status are reported. See "Power-on Sequence" in PG269 for more information.

    State values range from 0-15. A tile for the RFDC is considered operating nominally with valid
    data present on the interface when in state 15. If in any other state the RFDC is waiting for
    an electrical condition (sufficient power, clock presence, etc.). A summary of the mappings from
    state value to current seuqencing is as follows:

    0-2  : Device Power-up and Configuration
    3-5  : Power Supply adjustment
    6-10 : Clock configuration
    11-13: Converter Calibration (ADC only)
    14   : wait for deassertion of AXI4-Stream reset
    15   : Done, the rfdc is ready and operating

    :return: Dictionary for current enabled state of ADC/DACs
    :rtype: dict[str, int]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    reply, informs = t.katcprequest(name='rfdc-status', request_timeout=t._timeout)
    status = {}
    for i in informs:
      # example inform (same format for DAC): 'ADC0: Enabled 1, State 15, PLL' or 'ADC0: Enabled 0'
      info = i.arguments[0].decode().split(': ')
      tile = info[0]
      stat = info[1].split(', ')
      d = {}
      for s in stat:
        k, v = s.split(' ')
        d[k] = int(v)
      status[tile] = d

    return status


  def get_fabric_clk_freq(self, ntile, converter_type):
    """
    Get the clock frequency at the PL/fifo interface between the adc or dac indicated by "converter_type" on tile "ntile".  "converter_type"
    must be "adc" or "dac" and "ntile" must be in the range (0-3).

    :param ntile: Tile index of target converter, in the range (0-3)
    :type ntile: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str

    :return: fabric clk frequency in MHz, "None" if target converter tile is disabled
    :rtype: float
    """

    t = self.parent.transport

    args = (ntile, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-fab-clk-freq', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode()
    if info == "(disabled)":
      return None
    else:
      return float(info)


  def get_datatype(self, ntile, nblk, converter_type):
    """
    Get the output datetype of the adc or dac indicated by "converter_type" for the tile/block pair "ntile" and "nblk". "converter_type"
    must be "adc" or "dac" and "ntile" and "nblk" must both be in the range (0-3). Returning 0 represents real-valued data and 1 represents
    complex-valued data.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str

    :return: Integer value that is to map back to the converter output type, 0: real-valued, 1: complex-valued. Returns None if the target
    converter is disabled
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-datatype', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode()
    if info == "(disabled)":
      return None
    else:
      return int(info)


  def get_datawidth(self, ntile, nblk, converter_type):
    """
    Get the datawidth, in samples, at the PL/fifo interface between the adc or dac indicated by "converter_type" for the tile/block pair
    "ntile/nblk". "converter_type" must be "adc" or "dac" and "ntile" and "nblk" must both be in the range (0-3).

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str

    :return: Number of 16-bit samples at the output of the converter. Returns None if the target converter is disabled. For real-value
    output this is the same as the number of samples. For complex-valued outputs, this is the number I, or Q, samples at the output of the
    interface. On dual-tile platforms, this is the total number of 16-bit I and Q samples combined together.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-datawidth', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode()
    if info == "(disabled)":
      return None
    else:
      return int(info)


  def get_nyquist_zone(self, ntile, nblk, converter_type):
    """
    Get the nyquist zone setting for a specified adc/dac

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str

    :return: Currently configured Nyquist zone (1 or 2) for target converter. Returns None if converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-nyquist-zone', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None
    else:
      nyquist_zone = info[1]
      return int(nyquist_zone)


  def set_nyquist_zone(self, ntile, nblk, converter_type, nyquist_zone):
    """
    Set the nyquist zone for a specified adc/dac

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str
    :param nyquist_zone: target nyquist zone value (1 or 2)

    :return: Configured Nyquist zone for target converter. Returns None if converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac", nyquist_zone)
    reply, informs = t.katcprequest(name='rfdc-set-nyquist-zone', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None
    else:
      nyquist_zone = info[1]
      return int(nyquist_zone)


  def get_coarse_delay(self, ntile, nblk, converter_type):
    """
    Coarse delay allows adjusting the delay in the digital datapath, which can be useful to compensate for delay mismatch in a system
    implementation. The compensation here is limited to periods of the sampling clock. The following shows the number of periods of
    the sampling clock (T1 = sample clock period, or T2=2*T1, i.e., twice the sample period).

    Delay tuning capability in Gen 1/Gen 2 devices:

    Tile Type  | Digital Control | Coarse Delay Step
    ------------------------------------------------
    Dual Tile       0 to 7              T2
    Quad Tile       0 to 7              T1
    RF-DAC          0 to 7              T1

    Delay tuning capability in Gen 3 devices:

    All tile types have digital delay control 0-40 in coarse T1 delay steps.

    Note: for PCB design and flight time information to correct delay adjustment see the UltraScale Architecture PCB Design User Guide (UG583).

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str

    :return: Digital datapath coarse delay value in units of sample clock period as shown in above table. Returns None if the target
             converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-coarse-delay', request_timeout=t._timeout, request_args=args)

    coarse_delay = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return coarse_delay

    for stat in info:
      k,v = stat.split(' ')
      coarse_delay[k] = int(v)

    return coarse_delay


  def set_coarse_delay(self, ntile, nblk, converter_type, coarse_delay, event_source):
    """
    Coarse delay allows adjusting the delay in the digital datapath, which can be useful to compensate for delay mismatch in a system
    implementation. The compensation here is limited to periods of the sampling clock. The following shows the number of periods of
    the sampling clock (T1 = sample clock period, or T2=2*T1, i.e., twice the sample period).

    Delay tuning capability in Gen 1/Gen 2 devices:

    Tile Type  | Digital Control | Coarse Delay Step
    ------------------------------------------------
    Dual Tile       0 to 7              T2
    Quad Tile       0 to 7              T1
    RF-DAC          0 to 7              T1

    Delay tuning capability in Gen 3 devices:

    All tile types have digital delay control 0-40 in coarse T1 delay steps.

    Note: for PCB design and flight time information to correct delay adjustment see the UltraScale Architecture PCB Design User Guide (UG583).

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str
    :param coarse_delay: Coarse delay in the number of samples. Range: (0-7) for Gen 1/Gen 2 devices and (0-40) for Gen 3 devices.
    :type coarse_delay: int
    :param event_souce: Event source for update of coarse delay settings
    :type event_source: int

    :return: Digital datapath coarse delay value in units of sample clock period as shown in above table. Returns None if the target
             converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac", coarse_delay, event_source)
    reply, informs = t.katcprequest(name='rfdc-get-coarse-delay', request_timeout=t._timeout, request_args=args)

    coarse_delay = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return coarse_delay

    for stat in info:
      k,v = stat.split(' ')
      coarse_delay[k] = v

    return coarse_delay


  def get_qmc_settings(self, ntile, nblk, converter_type):
    """
    Get quadrature modulator correction (QMC) settings for target converter.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str

    :return: dictionary of QMC settings. Returns None if the target converter is disabled.
    :rtype: dict[str, float]
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-qmc-settings', request_timeout=t._timeout, request_args=args)

    qmc_settings = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return qmc_settings

    for stat in info:
      k,v = stat.split(' ')
      qmc_settings[k] = float(v)

    return qmc_settings


  def set_qmc_settings(self, ntile, nblk, converter_type, enable_phase, phase_correction_factor,
                        enable_gain, gain_correction_factor,
                        offset_correction_factor, event_source):
    """
    Set quadrature modulator correction (QMC) settings for target converter. The QMC is used to correct imbalance in I/Q datapaths
    after front end analog conversion. Error and/or imbalance detection is an application specific process.

    # set QMC settings to adjust gain and phase for adc 0 in tile 0 to update with a tile event
    rfdc.set_qmc_settings(0,0, rfdc.ADC_TILE, 1, -5.0, 1, 0.9, 0, rfdc.EVNT_SRC_TILE)
    # set QMC settings for adc 1 to just adjust gain in tile 0 to update with a tile event
    rfdc.set_qmc_settings(0,1, rfdc.ADC_TILE, 0, 0, 1, 0.95, 0, rfdc.EVNT_SRC_TILE)
    # generate a tile update event to apply QMC settings, both are in the same tile needing to specify the event once using either 0 or 1
    rfdc.update_event(0, 0, rfdc.ADC_TILE, rfdc.EVENT_QMC)

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str
    :param enable_phase: Indicates if phase is enabled (1) or disabled (0).
    :type enable_phase: int
    :param phase_correction_factor: Phase correction factor. Range: +/- 26.5 degrees (Exclusive).
    :type phase_correction_factor: float
    :param enable_gain: Indicates if gain is enabled(1) or disabled (0).
    :type enable_gain: int
    :param gain_correction_factor: Gain correction factor. Range: 0 to 2.0 (Exclusive).
    :type gain_correction_factor: float
    :param offset_correction_factor: Offset correction factor is adding a fixed LSB value to the sampled signal.
    :type offset_correction_factor: int
    :param event_source: Event source for QMC settings.
    :type event_source: int

    :return: dictionary of applied QMC settings. Returns None if the target converter is disabled.
    :rtype: dict[str, float]
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac", enable_phase, enable_gain,
            gain_correction_factor, phase_correction_factor, offset_correction_factor, event_source)
    reply, informs = t.katcprequest(name='rfdc-set-qmc-settings', request_timeout=t._timeout, request_args=args)

    qmc_settings = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return qmc_settings

    for stat in info:
      k,v = stat.split(' ')
      qmc_settings[k] = float(v)

    return qmc_settings


  def update_event(self, ntile, nblk, converter_type, event):
    """
    Use this function to trigger the update event for an event if the event source is Slice or Tile.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str
    :param event: trigger update event for mixer, coarse delay, or qmc.
    :type event: int

    :return: None
    :rtype: None
    """
    t = self.parent.transport

    args = (ntile, nblk, "adc" if converter_type == self.ADC_TILE  else "dac", event)
    reply, informs = t.katcprequest(name='rfdc-update-event', request_timeout=t._timeout, request_args=args)


  def get_pll_config(self, ntile, converter_type):
    """
    Reads the PLL settings for a converter tile.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param converter_type: Represents the target converter type, "adc" or "dac"
    :type converter_type: str

    :return: Dictionary with converter tile PLL settings, empty dictionary if tile/block is disabled
    :rtype: dict[str, float]
    """
    t = self.parent.transport

    args = (ntile, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-pll-config', request_timeout=t._timeout, request_args=args)

    pll_config = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return pll_config

    for stat in info:
      k,v = stat.split(' ')
      pll_config[k] = float(v)

    return pll_config


  def set_pll_config(self, ntile, converter_type, clk_src, pll_ref_freq, sample_rate):
    """
    Dyanmically configure PLL settings for a converter tile.

    :param ntile: Tile index of where target converter block is, in the range (0-3).
    :type ntile: int
    :param converter_type: Represents the target converter type, "adc" or "dac".
    :type converter_type: str
    :param clk_src: Internal PLL or external clock source.
    :type clk_src: int
    :param pll_ref_freq: Reference clock frequency in MHz (FREF min to FREF max).
    :type pll_ref_freq: float
    :param sample_rate: Sampling rate frequency in MHz (Fs min to Fs max).
    :type sample_rate: float

    :return: Dictionary with converter tile PLL settings, empty dictionary if tile/block is disabled.
    :rtype: dict[str, float]
    """
    t = self.parent.transport

    args = (ntile, "adc" if converter_type == self.ADC_TILE  else "dac", clk_src, pll_ref_freq, sample_rate)
    reply, informs = t.katcprequest(name='rfdc-set-pll-config', request_timeout=t._timeout, request_args=args)

    pll_config = {}
    if len(informs) > 0: # (disabled) response, the only time this function informs is if the tile is disabled
      return pll_config

    return self.get_pll_config(ntile, converter_type)


  def get_pll_lock_status(self, ntile, converter_type):
    """
    Gets the PLL lock status for target converter tile.

    :param ntile: Tile index of where target converter block is, in the range (0-3).
    :type ntile: int
    :param converter_type: Represents the target converter type, "adc" or "dac".
    :type converter_type: str

    :return: PLL lock status, empty if tile/block is disabled or internal PLL not used.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-pll-lock-status', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    pll_lock_status = info[1]
    if info == "(disabled)":
      return None
    else:
      return int(pll_lock_status)


  def get_clk_src(self, ntile, converter_type):
    """
    Gets the source for target converter tile sample clock (external or internal PLL).

    :param ntile: Tile index of where target converter block is, in the range (0-3).
    :type ntile: int
    :param converter_type: Represents the target converter type, "adc" or "dac".
    :type converter_type: str

    :return: Source for sample clock, 0: external, 1: internal PLL, empty if tile is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, "adc" if converter_type == self.ADC_TILE  else "dac")
    reply, informs = t.katcprequest(name='rfdc-get-clk-src', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    clk_src = info[1]
    if info == "(disabled)":
      return None
    else:
      return int(clk_src)


  def get_dsa(self, ntile, nblk):
    """
    Get the step attenuator (DSA) value for an enaled ADC block. If a tile/block pair is disabled
    an empty dictionary is returned and nothing is done.

    :param ntile: Tile index of target block to apply attenuation, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target adc to apply attenuation, must be in the range (0-3)
    :type nblk: int

    :return: Dictionary with dsa value, empty dictionary if tile/block is disabled
    :rtype: dict[str, str]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk)
    reply, informs = t.katcprequest(name='rfdc-get-dsa', request_timeout=t._timeout, request_args=args)

    dsa = {}
    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return dsa

    k = info[0]
    v = info[1]
    dsa = {k:v}
    return dsa


  def set_dsa(self, ntile, nblk, atten_dB):
    """
    Set the digital step attenuator (DSA) of enabled tile "ntile" and adc block "nblk" to the
    value specified by `atten_dB`.

    After write the attenuation value is read and. If a tile/blk pair is disabled an empty
    dictionary is returned and nothing is done.

    ES1 silicon can command attenuation levels from 0-11 dB with a step of 0.5 dB. Production
    silicon can command to levels 0-27 dB with a step of 1.0 dB.

    See Xilinx/AMD PG269 for more details on the DSA in the RFDC. This is only available on
    Gen 3 devices.

    :param ntile: Tile index of target block to apply attenuation, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target adc to apply attenuation, must be in the range (0-3)
    :type nblk: int
    :param atten_dB: Requested attenuation level
    :type float:

    :return: Dictionary with dsa value, empty dictionary if tile/block is disabled
    :rtype: dict[str, str]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk, atten_dB,)
    reply, informs = t.katcprequest(name='rfdc-set-dsa', request_timeout=t._timeout, request_args=args)

    dsa = {}
    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return dsa

    k = info[0]
    v = info[1]
    dsa = {k:v}
    return dsa


  def get_cal_freeze(self, ntile, nblk):
    """
    Get the adc calibration freeze status for enabled tile "ntile" and block index "nblk". If a tile/block
    pair is disabled an empty dictionary is returned and nothing is done.

    :param ntile: Tile index of target adc tile to get calibration freeze status, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target adc block to get output current, must be in the range (0-3)
    :type nblk: int

    :return: Dictionary with freeze settings, empty dictionary if tile/block is disabled
    :rtype: dict[str, int]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk)
    reply, informs = t.katcprequest(name='rfdc-get-cal-freeze', request_timeout=t._timeout, request_args=args)

    freeze_settings = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return freeze_settings

    for stat in info:
      k,v = stat.split(' ')
      freeze_settings[k] = v

    return freeze_settings


  def set_cal_freeze(self, ntile, nblk, freeze):
    """
    Set adc calibration freeze status for enabled tile "ntile" and block index "nblk". If a tile/block
    pair is disabled an empty dictionary is returned and nothing is done.

    :param ntile: Tile index of target adc tile to get calibration freeze status, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target adc block to get output current, must be in the range (0-3)
    :type nblk: int
    :param freeze: 1 - indicates the calibration should be frozen. 0 - calibration should be unfrozen.

    :return: Dictionary with freeze settings after applying new freeze value, empty dictionary if tile/block is disabled.
    Freeze settings fields are:
      - CalFrozen: indicates the current status of the background calibration functions. 1 - indicates the calibration
        is frozen; 0 - indicates background calibration is operating normally.
      - DisableFreezePin: this is not accessible by the casperfpga api at the moment
      - FreezeCalibration: software register controling freeze calibration from the driver (this is what is set to freeze
        the calibration). If this value is set calibration should also be frozen as indicated by "CalFrozen".
    :rtype: dict[str, int]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk, freeze)
    reply, informs = t.katcprequest(name='rfdc-set-cal-freeze', request_timeout=t._timeout, request_args=args)

    freeze_settings = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return freeze_settings

    for stat in info:
      k,v = stat.split(' ')
      freeze_settings[k] = v

    return freeze_settings


  def get_cal_coeffs(self, ntile, nblk, calblk):
    """
    Get the adc calibration coefficients for enabled tile "ntile" and block index "nblk" for the background calibration blocks. If a
    tile/block pair is disabled an empty dictionary is returned and nothing is done. Valid calblk values are 0 (for gen3 devices) 1-3 and
    represent the OCB1, OCB2, GCB, and TSCB background calibration blocks, respectively. A user can also use rfdc.OCB1, rfdc.OCB2, rfdc.GCB, and
    rfdc.TSCB to target calibration blocks, E.g., `get_cal_coeffs(0, 0, rfdc.OCB2)`.

    Coeff{4-7} applies when chopping is active and is only relevant to the time skew calibration block (TSCB).

    :param ntile: Tile index of target adc tile to get calibration freeze status, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target adc block to get output current, must be in the range (0-3)
    :type nblk: int
    :param calblk: Calibration block index, range 0 (for gen3 devices only) 1-3 representing the OCB1, OCB2, GCB, and TSCB respectively.
    :type calblk: int

    :return: Dictionary with calibration coefficients, empty dictionary if tile/block is disabled
    :rtype: dict[str, int]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk, calblk)
    reply, informs = t.katcprequest(name='rfdc-get-cal-coeffs', request_timeout=t._timeout, request_args=args)

    cal_coeffs = {}
    info = informs[0].arguments[0].decode().split(', ')
    if len(info) == 1: # (disabled) response
      return cal_coeffs

    for stat in info:
      k,v = stat.split(' ')
      cal_coeffs[k] = v

    return cal_coeffs


  def set_cal_coeffs(self, ntile, nblk, calblk, coeffs):
    """
    Set adc calibration coefficients for enabled tile "ntile" and block index "nblk" for the background calibration blocks. If a tile/block
    pair is disabled an empty dictionary is returned and nothing is done. Valid calblk values are 0 (for gen3 devices) 1-3 and represent the
    OCB1, OCB2, GCB, and TSCB background calibration blocks, respectively. A user can also use rfdc.OCB1, rfdc.OCB2, rfdc.GCB, and rfdc.TSCB to
    target calibration blocks, E.g., `get_cal_coeffs(0, 0, rfdc.OCB2)`.

    :param ntile: Tile index of target adc tile to get calibration freeze status, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target adc block to get output current, must be in the range (0-3)
    :type nblk: int
    :param calblk: Calibration block index, range 0 (for gen3 devices only) 1-3 representing the OCB1, OCB2, GCB, and TSCB respectively.
    :type calblk: int
    :param coeffs: list of eight calibration coefficients
    :type coeffs: list[int]

    :return: Dictionary with calibration coefficients, empty dictionary if tile/block is disabled
    :rtype: dict[str, int]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk, calblk, *coeffs)
    reply, informs = t.katcprequest(name='rfdc-set-cal-coeffs', request_timeout=t._timeout, request_args=args)

    cal_coeffs = {}

    if len(informs) > 0: # (disabled) response, the only time this function informs is if the tile is disabled
      return cal_coeffs

    args = (ntile, nblk, calblk)
    reply, informs = t.katcprequest(name='rfdc-get-cal-coeffs', request_timeout=t._timeout, request_args=args)

    cal_coeffs = {}
    info = informs[0].arguments[0].decode().split(', ')

    for stat in info:
      k,v = stat.split(' ')
      cal_coeffs[k] = v

    return cal_coeffs


  def disable_user_coeffs(self, ntile, nblk, calblk):
    """
    Disables calibration coefficients for calibration block "calblk" set by the user from a call to "set_cal_coeffs()" for target adc 
    indicated by "ntile" and "nblk". A call to "get_cal_coeffs()" is required to show coeffs have been cleared of user values.

    :param ntile: Tile index of target adc, in the range (0-3).
    :type ntile: int
    :param nblk: Block index of target adc within a tile, in the range (0-3).
    :type nblk: int
    :param calblk: Calibration block index, range 0 (for gen3 devices only) 1-3 representing the OCB1, OCB2, GCB, and TSCB respectively.
    :type calblk: int

    :return: None

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk, calblk)
    reply, informs = t.katcprequest(name='rfdc-disable-user-coeffs', request_timeout=t._timeout, request_args=args)


  def get_cal_mode(self, ntile, nblk):
    """
    Get the calibration mode for target converter selected by the tile/blk pair "ntile"/"nblk". It a tile pair is disabled None is returned.

    :param ntile: Tile index of target adc, in the range (0-3).
    :type ntile: int
    :param nblk: Block index of target adc within a tile, in the range (0-3).
    :type nblk: int

    :return: Integer representing calibration Mode, 1: Mode 1, 2: Mode 2. None if target adc is disabled.
    :rtype: int

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk)
    reply, informs = t.katcprequest(name='rfdc-get-cal-mode', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None

    return int(info[1])

  def set_cal_mode(self, ntile, nblk, calmode):
    """
    Set the calibration mode for target converter selected by the tile/blk pair "ntile"/"nblk". It a tile pair is disabled None is returned.

    :param ntile: Tile index of target adc, in the range (0-3).
    :type ntile: int
    :param nblk: Block index of target adc within a tile, in the range (0-3).
    :type nblk: int
    :param calmode: Calibration mode to run on target converter, 1: Mode 1, 2: Mode 2.
    :type calmode: int

    :return: Integer representing calibration Mode, 1: Mode 1, 2: Mode 2. None if target adc is disabled.
    :rtype: int

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk, calmode)
    reply, informs = t.katcprequest(name='rfdc-set-cal-mode', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None

    return int(info[1])


  def get_output_current(self, ntile, nblk):
    """
    Get the output current in micro amps of enabled tile "ntile" and dac block "nblk". If a tile/block
    pair is disabled an empty dictionary is returned and nothing is done.

    :param ntile: Tile index of target dac tile to get output current, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target dac block to get output current, must be in the range (0-3)
    :type nblk: int

    :return: Dictionary with current value in micro amp, empty dictionary if tile/block is disabled
    :rtype: dict[str, str]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk)
    reply, informs = t.katcprequest(name='rfdc-get-output-current', request_timeout=t._timeout, request_args=args)

    current = {}
    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return {}

    k = info[0]
    v = info[1]
    current = {k:v}
    return current


  def set_vop(self, ntile, nblk, curr_uA):
    """
    Set the output current in micro amps of enabled tile "ntile" and dac block "nblk". If a tile/block
    pair is disabled an empty dictionary is returned and nothing is done.

    ES1 silicon can command ranges from 6425 to 32000. Production silicon can accept values in the
    range 2250 to 40500. Values are rounded to the nearest increment managed by the rfdc driver. Ranges,
    errors, and bound checks are performed by the driver.

    See Xilinx/AMD PG269 for more details on the VOP capabilities of the RFDC. This Only available on
    Gen 3 device.

    :param ntile: Tile index of target block to get output current, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target dac get output current, must be in the range (0-3)
    :type nblk: int
    :param curr_uA: the desired output current in micro amps
    :type curr_uA: int

    :return: Dictionary with current value in micro amp, empty dictionary if tile/block is disabled
    :rtype: dict[str, str]

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport

    args = (ntile, nblk, curr_uA,)
    reply, informs = t.katcprequest(name='rfdc-set-vop', request_timeout=t._timeout, request_args=args)

    vop = {}
    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: #(disabled) response
      return vop

    k = info[0]
    v = info[1]
    vop = {k:v}
    return vop


  def get_invsinc_fir(self, ntile, nblk):
    """
    Get the inverse sinc filter mode.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int

    :return: 0 if disabled, 1 if first nyquist, and 2 for second nyquist (gen 3 devices only). Returns None if converter is disabled.
    """
    t = self.parent.transport

    args = (ntile, nblk)
    reply, informs = t.katcprequest(name='rfdc-get-invsincfir', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None
    else:
      invsincfir_mode = info[1]
      return int(invsincfir_mode)


  def set_invsinc_fir(self, ntile, nblk, invsinc_fir_mode):
    """
    Set the inverse sinc filter mode; 0 - disabled, 1 - first nyquist, and for gen 3 devices 2 - second nyquist.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param invsinc_fir_mode: inverse sinc filter mode; 0 - disabled, 1 - first nyquist, and for gen 3 devices 2 - second nyquist.

    :type invsinc_fir_mode: int

    :return: 0 if disabled, 1 if first nyquist, and 2 for second nyquist (gen 3 devices only). Returns None if converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, invsinc_fir_mode)
    reply, informs = t.katcprequest(name='rfdc-set-invsincfir', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None
    else:
      invsincfir_mode = info[1]
      return int(invsincfir_mode)


  def invsinc_fir_enabled(self, ntile, nblk):
    """
    If the inverse sinc filter is enabled for target DAC converter, the function returns 1; otherwise, it returns 0.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int

    :return: 1 if filter is enabled; otherwise, returns 0. Returns None if converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk)
    reply, informs = t.katcprequest(name='rfdc-invsincfir-enabled', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None
    else:
      invsincfir_enabled = info[1]
      return int(invsincfir_enabled)


  def get_imr_mode(self, ntile, nblk):
    """
    Get the image rejection filter mode.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int

    :return: 0 if in lowpass mode, 1 if highpass mode. Returns None if converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk)
    reply, informs = t.katcprequest(name='rfdc-get-imr-mode', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None
    else:
      imr_mode = info[1]
      return int(imr_mode)


  def set_imr_mode(self, ntile, nblk, imr_mode):
    """
    Set the image rejection filter mode; 0 - lowpass, 1 - highpass.

    :param ntile: Tile index of where target converter block is, in the range (0-3)
    :type ntile: int
    :param nblk: Block index within target converter tile, in the range (0-3)
    :type nblk: int
    :param imr_mode: IMR filter mode set to 0 for lowpass or 1 for high pass.

    :return: 0 if in lowpass mode, 1 if highpass mode. Returns None if converter is disabled.
    :rtype: int
    """
    t = self.parent.transport

    args = (ntile, nblk, imr_mode)
    reply, informs = t.katcprequest(name='rfdc-set-imr-mode', request_timeout=t._timeout, request_args=args)

    info = informs[0].arguments[0].decode().split(' ')
    if len(info) == 1: # (disabled) response
      return None
    else:
      imr_mode = info[1]
      return int(imr_mode)


  def run_mts(self, tile_mask=15, target_latency=None):
    """
    Execute multi-tile synchronization (MTS) to synchronize ADC tiles set by "tile_mask".
    Optionally request to synch with latency specified by "target_latency".

    :param mask: Bitmask for selecting which tiles to sync, defaults to all tiles 0x1111 = 15. LSB is ADC Tile 0.
    :type mask: int

    :param target_latency: Requested target latency
    :type target_latency: int

    :return: `True` if completes successfuly, `False` otherwise
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """

    if target_latency is not None:
      print("WARN: 'target_latency' not yet implemented, this argument is ignored")

    t = self.parent.transport
    self.mts_report = []
    args = (tile_mask,)
    reply, informs = t.katcprequest(name='rfdc-run-mts', request_timeout=t._timeout, request_args=args)
    for i in informs:
      self.mts_report.append(i)

    return True


  def get_mts_report(self):
    """
    Prints a detailed report of the most recent multi-tile synchronization run. Including information
    such as latency on each tile, delay maker, delay bit.

    :return: `True` if completes successfuly, `False` otherwise
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    for m in self.mts_report:
      print(m)

    return True


  def update_nco_mts(self, adc_mask, dac_mask, freq):
    """
    Program and updates NCOs on board while maintaining multi-tile synchronization.

    :param adc_mask: 16 bits indicating what ADCs to set. LSB is ADC 00
    :type adc_mask: int

    :param dac_mask: 16 bits indicating what DACs to set. LSB is DAC 00
    :type dac_mask: int

    :param freq: Frequency in MHz to set the NCO to
    :type freq: float

    :return: `True` if completes successfuly, `False` otherwise
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport
    args = (adc_mask, dac_mask, freq,)
    reply, informs = t.katcprequest(name='rfdc-update-nco-mts', request_timeout=t._timeout, request_args=args)
    for i in informs:
      print(i)
    return True


  def report_mixer_status(self, adc_mask, dac_mask):
    """
    Retrieves and reports mixer settings from rfdc.

    :param adc_mask: 16 bits indicating what ADCs to set. LSB is ADC 00
    :type adc_mask: int

    :param dac_mask: 16 bits indicating what DACs to set. LSB is DAC 00
    :type dac_mask: int

    :return: `True` if completes successfuly, `False` otherwise
    :rtype: bool

    :raises KatcpRequestFail: If KatcpTransport encounters an error
    """
    t = self.parent.transport
    for tile in range(0,4):
      for blk in range(0,4):
        if (adc_mask >> (tile*4+blk)) & 1:
          args = (tile, blk, "adc")
          reply, informs = t.katcprequest(name='rfdc-report-mixer', request_timeout=t._timeout, request_args=args)
          print("ADC {:d} {:d} mixer settings:".format(tile,blk))
          for i in informs:
            print("\t" + i.arguments[0].decode())

    for tile in range(0,4):
      for blk in range(0,4):
        if (dac_mask >> (tile*4+blk)) & 1:
          args = (tile, blk, "dac")
          reply, informs = t.katcprequest(name='rfdc-report-mixer', request_timeout=t._timeout, request_args=args)
          print("DAC {:d} {:d} mixer settings:".format(tile,blk))
          for i in informs:
            print("\t" + i.arguments[0].decode())

    return True


  def get_adc_snapshot(self, ntile, nblk):
    """
    """
    raise NotImplemented()


