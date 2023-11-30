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


  def get_output_current(self, ntile, nblk):
    """
    Get the output current in micro amps of enabled tile "ntile" and dac block "nblk". If a tile/block
    pair is disabled an empty dictionary is returned and nothing is done.

    :param ntile: Tile index of target block to get output current, in the range (0-3)
    :type ntile: int
    :param nblk: Block index of target dac get output current, must be in the range (0-3)
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


