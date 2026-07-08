"""
EVE Marshal Opcodes (from EvEmu EVEMarshalOpcodes.h)

These are the wire opcodes for EVE's custom Python marshal format.
"""

Op_PyNone = 0x01
Op_PyToken = 0x02
Op_PyLongLong = 0x03
Op_PyLong = 0x04
Op_PySignedShort = 0x05
Op_PyByte = 0x06
Op_PyMinusOne = 0x07
Op_PyZeroInteger = 0x08
Op_PyOneInteger = 0x09
Op_PyReal = 0x0A
Op_PyZeroReal = 0x0B
Op_PyBuffer = 0x0D
Op_PyEmptyString = 0x0E
Op_PyCharString = 0x0F
Op_PyShortString = 0x10
Op_PyStringTableItem = 0x11
Op_PyWStringUCS2 = 0x12
Op_PyLongString = 0x13
Op_PyTuple = 0x14
Op_PyList = 0x15
Op_PyDict = 0x16
Op_PyObject = 0x17
Op_PySubStruct = 0x19
Op_PySavedStreamElement = 0x1B
Op_PyChecksumedStream = 0x1C
Op_PyTrue = 0x1F
Op_PyFalse = 0x20
Op_cPicked = 0x21
Op_PyObjectEx1 = 0x22
Op_PyObjectEx2 = 0x23
Op_PyEmptyTuple = 0x24
Op_PyOneTuple = 0x25
Op_PyEmptyList = 0x26
Op_PyOneList = 0x27
Op_PyEmptyWString = 0x28
Op_PyWStringUCS2Char = 0x29
Op_PyPackedRow = 0x2A
Op_PySubStream = 0x2B
Op_PyTwoTuple = 0x2C
Op_PackedTerminator = 0x2D
Op_PyWStringUTF8 = 0x2E
Op_PyVarInteger = 0x2F
