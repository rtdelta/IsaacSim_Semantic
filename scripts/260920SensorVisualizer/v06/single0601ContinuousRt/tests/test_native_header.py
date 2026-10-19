"""The native decoder must reject bad ABI bytes before calling an SDK parser."""
import struct
import unittest
from single0601_continuous_rt.common import ContractError
from single0601_continuous_rt.native_header import decode_header


class NativeHeaderTests(unittest.TestCase):
    def packet(self):
        data=bytearray(264)
        struct.pack_into('<4IQI',data,0,0x4E474D4F,1,0,0,264,7)
        struct.pack_into('<2H2Q2I',data,28,0,0,9007199254740993,12345678901234567,0,0)
        struct.pack_into('<16f',data,56,*[1. if i in (0,5,10,15) else 0. for i in range(16)])
        struct.pack_into('<Q7f',data,120,12345678901234566,0.,0.,0.,1.,1.,2.,3.)
        struct.pack_into('<Q7f',data,160,12345678901234567,0.,0.,1.,0.,4.,5.,6.)
        return data
    def test_large_integer_and_frame_fields(self):
        header=decode_header(self.packet(),full_packet=True)
        self.assertEqual(header['native_frame_id'],'9007199254740993')
        self.assertEqual(header['frame_end']['timestamp_ns'],'12345678901234567')
        self.assertEqual(header['frame_end']['orientation_raw'],[0.,0.,1.,0.])
        self.assertEqual(header['frame_end']['position_m'],[4.,5.,6.])
    def test_unsupported_truncated_or_nonfinite_rejected(self):
        with self.assertRaises(ContractError):decode_header(self.packet()[:263])
        data=self.packet();struct.pack_into('<I',data,4,2)
        with self.assertRaises(ContractError):decode_header(data)
        data=self.packet();struct.pack_into('<f',data,168,float('nan'))
        with self.assertRaises(ContractError):decode_header(data)
    def test_prefix_does_not_dereference_pointer_or_require_whole_packet(self):
        data=self.packet();struct.pack_into('<Q',data,16,4096);struct.pack_into('<Q',data,208,0xffffffffffffffff)
        self.assertEqual(decode_header(data)['declared_packet_bytes'],4096)
        with self.assertRaises(ContractError):decode_header(data,full_packet=True)


if __name__=='__main__':unittest.main()
