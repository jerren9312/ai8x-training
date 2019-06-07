###################################################################################################
# Copyright (C) 2018-2019 Maxim Integrated Products, Inc. All Rights Reserved.
#
# Maxim Confidential
#
# Written by RM
###################################################################################################
"""
Routines to read and write the APB peripherals.
"""
import sys

import tornadocnn


class APB(object):
    """
    APB read and write functionality.
    """

    def __init__(self, memfile, apb_base, block_mode=False,
                 verify_writes=False, no_error_stop=False):
        """
        Create an APB class object that writes to memfile.
        """
        self.memfile = memfile
        self.foffs = 0
        self.apb_base = apb_base
        self.verify_writes = verify_writes
        self.no_error_stop = no_error_stop
        self.data = 0
        self.num = 0
        self.data_offs = 0
        self.mem = [False] * tornadocnn.C_GROUP_OFFS * tornadocnn.P_NUMGROUPS

        if block_mode:
            self.write = self.write_block
            self.verify = self.verify_block
        else:
            self.write = self.write_top
            self.verify = self.verify_top

    def write_block(self, addr, val,
                    comment='', no_verify=False):  # pylint: disable=unused-argument
        """
        Write address `addr` and data `val` to the .mem file.
        """
        assert val >= 0
        assert addr >= 0
        addr += self.apb_base

        self.memfile.write(f'@{self.foffs:04x} {addr:08x}\n')
        self.memfile.write(f'@{self.foffs+1:04x} {val:08x}\n')
        self.foffs += 2

    def write_top(self, addr, val, comment='', no_verify=False):
        """
        Write address `addr` and data `val` to the .c file.
        if `no_verify` is `True`, do not check the result of the write operation, even if
        `verify_writes` is globally enabled.
        An optional `comment` can be added to the output.
        """
        assert val >= 0
        assert addr >= 0
        addr += self.apb_base

        self.memfile.write(f'  *((volatile uint32_t *) 0x{addr:08x}) = 0x{val:08x};{comment}\n')
        if self.verify_writes and not no_verify:
            self.memfile.write(f'  if (*((volatile uint32_t *) 0x{addr:08x}) != 0x{val:08x}) '
                               'return 0;\n')

    def verify_block(self, addr, val, comment='', rv=False):  # pylint: disable=unused-argument
        """
        Verify that memory at address `addr` contains data `val`.
        In `block_mode`, this function does nothing useful.
        """
        assert val >= 0
        assert addr >= 0

    def verify_top(self, addr, val, comment='', rv=False):
        """
        Verify that memory at address `addr` contains data `val`.
        If `rv` is `True`, do not immediately return 0, but just set the status word.
        An optional `comment` can be added to the output.
        """
        assert val >= 0
        assert addr >= 0
        addr += self.apb_base

        if rv:
            self.memfile.write(f'  if (*((volatile uint32_t *) 0x{addr:08x}) != 0x{val:08x}) '
                               f'return 0;{comment}\n')  # FIXME
        else:
            self.memfile.write(f'  if (*((volatile uint32_t *) 0x{addr:08x}) != 0x{val:08x}) '
                               f'return 0;{comment}\n')

    def set_memfile(self, memfile):
        """
        Change the file handle to `memfile` and reset the .mem output location to 0.
        """
        self.memfile = memfile
        self.foffs = 0

    def write_ctl(self, group, reg, val, debug=False, comment=''):
        """
        Set global control register `reg` in group `group` to value `val`.
        """
        if comment is None:
            comment = f' // global ctl {reg}'
        addr = tornadocnn.C_GROUP_OFFS*group + tornadocnn.C_CNN_BASE + reg*4
        self.write(addr, val, comment)
        if debug:
            print(f'R{reg:02} ({addr:08x}): {val:08x}{comment}')

    def write_lreg(self, group, layer, reg, val, debug=False, comment=''):
        """
        Set layer `layer` register `reg` in group `group` to value `val`.
        """
        if comment is None:
            comment = f' // reg {reg}'
        addr = tornadocnn.C_GROUP_OFFS*group + tornadocnn.C_CNN_BASE + tornadocnn.C_CNN*4 \
            + reg*4 * tornadocnn.MAX_LAYERS + layer*4
        self.write(addr, val, comment)
        if debug:
            print(f'G{group} L{layer} R{reg:02} ({addr:08x}): {val:08x}{comment}')

    def write_bias(self, group, offs, bias):
        """
        Write bias value `bias` to offset `offs` in bias memory #`group`.
        """
        addr = tornadocnn.C_GROUP_OFFS*group + tornadocnn.C_BRAM_BASE + offs * 4
        self.write(addr, bias & 0xff, f' // Bias')

    def write_tram(self, group, proc, offs, d, comment=''):
        """
        Write value `d` to TRAM in group `group` and processor `proc` to offset `offs`.
        """
        addr = tornadocnn.C_GROUP_OFFS*group + tornadocnn.C_TRAM_BASE \
            + proc * tornadocnn.TRAM_SIZE * 4 + offs * 4
        self.write(addr, d, f' // {comment}TRAM G{group} P{proc} #{offs}')

    def write_kern(self, ll, ch, idx, k):
        """
        Write single 3x3 kernel `k` for layer `ll`, channel `ch` to index `idx` in weight
        memory.
        """
        assert ch < tornadocnn.MAX_CHANNELS
        assert idx < tornadocnn.MASK_WIDTH
        addr = tornadocnn.C_GROUP_OFFS * (ch // tornadocnn.P_NUMPRO) \
            + tornadocnn.C_MRAM_BASE \
            + (ch % tornadocnn.P_NUMPRO) * tornadocnn.MASK_WIDTH * 16 + idx * 16

        self.write(addr, k[0] & 0xff, no_verify=True,
                   comment=f' // Layer {ll}: processor {ch} kernel #{idx}')
        self.write(addr+4, (k[1] & 0xff) << 24 | (k[2] & 0xff) << 16 |
                   (k[3] & 0xff) << 8 | k[4] & 0xff, no_verify=True)
        self.write(addr+8, (k[5] & 0xff) << 24 | (k[6] & 0xff) << 16 |
                   (k[7] & 0xff) << 8 | k[8] & 0xff, no_verify=True)
        self.write(addr+12, 0, no_verify=True)  # Execute write
        if self.verify_writes:
            self.verify(addr, k[0] & 0xff)
            self.verify(addr+4, (k[1] & 0xff) << 24 | (k[2] & 0xff) << 16 |
                        (k[3] & 0xff) << 8 | k[4] & 0xff)
            self.verify(addr+8, (k[5] & 0xff) << 24 | (k[6] & 0xff) << 16 |
                        (k[7] & 0xff) << 8 | k[8] & 0xff)
            self.verify(addr+12, 0)

    def write_byte_flush(self, offs, comment=''):
        """
        Flush the contents of the internal buffer at offset `offs`, adding an optional
        `comment` to the output.
        This function also keeps track of all addresses that have been written before and
        can detect whether previous information is being overwritten.
        """
        if self.num > 0:
            woffs = self.data_offs - self.num
            if self.mem[woffs >> 2]:
                print(f'Overwriting location {woffs:08x}')
                if not self.no_error_stop:
                    sys.exit(1)
            self.write(woffs, self.data, comment)
            self.mem[woffs >> 2] = True
            self.num = 0
            self.data = 0
        self.data_offs = offs

    def write_byte(self, offs, val, comment=''):
        """
        Add byte `val` that should be written at offset `offs` to the internal buffer.
        When reaching 4 bytes, or when the offset is not contiguous, pad with zeros and
        flush the before adding the new value to the buffer.
        An optional `comment` can be added to the output.
        """
        if offs != self.data_offs:
            self.write_byte_flush(offs)

        # Collect and write if multiple of 4 (little endian byte order)
        self.data |= (val & 0xff) << (8*self.num)
        self.num += 1
        self.data_offs += 1
        if self.num == 4:
            self.write_byte_flush(offs+1, comment)

    def get_mem(self):
        """
        Return reference to the memory array.
        """
        return self.mem