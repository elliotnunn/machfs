`machfs` is a pure Python 3 library for reading and writing disk images in the
Apple's long-deprecated [Hierarchical File
System](https://en.wikipedia.org/wiki/Hierarchical_File_System) format. It
operates entirely on in-memory `bytes` objects. Images are serialised and
deserialised in one go using the `read` and `write` methods of the `Volume`
object.

The directory hierarchy of a `Volume` is then accessed and manipulated like a
Python `dict`. `Folder` and `File` objects represent the contents of the
filesystem.
