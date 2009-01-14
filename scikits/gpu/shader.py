"""
This module is based on code from

http://swiftcoder.wordpress.com/2008/12/19/simple-glsl-wrapper-for-pyglet/

which is

Copyright (c) 2008, Tristam MacDonald

Permission is hereby granted, free of charge, to any person or organization
obtaining a copy of the software and accompanying documentation covered by
this license (the "Software") to use, reproduce, display, distribute,
execute, and transmit the Software, and to prepare derivative works of the
Software, and to permit third-parties to whom the Software is furnished to
do so, all subject to the following:

The copyright notices in the Software and this entire statement, including
the above license grant, this restriction and the following disclaimer,
must be included in all copies of the Software, in whole or in part, and
all derivative works of the Software, unless such copies or derivative
works are solely in the form of machine-executable object code generated by
a source language processor.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, TITLE AND NON-INFRINGEMENT. IN NO EVENT
SHALL THE COPYRIGHT HOLDERS OR ANYONE DISTRIBUTING THE SOFTWARE BE LIABLE
FOR ANY DAMAGES OR OTHER LIABILITY, WHETHER IN CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

"""

__all__ = ['Program', 'VertexShader', 'FragmentShader', 'Shader',
           'default_vertex_shader']

from scikits.gpu.config import GLSLError

from pyglet.gl import *

class Shader:
    def __init__(self, source="", type='vertex'):
        """
        Vertex, Fragment, or Geometry shader.

        Parameters
        ----------
        source : string or list
            String or list of strings.  The GLSL source code for the shader.
        type : {'vertex', 'fragment', 'geometry'}
            Type of shader.

        """
        shader_type = {'vertex': GL_VERTEX_SHADER,
                       'fragment': GL_FRAGMENT_SHADER,}
##                       'geometry': GL_GEOMETRY_SHADER}

        # create the vertex shader
        self._createShader(source, shader_type[type])

    def _createShader(self, strings, type):
        if isinstance(strings, basestring):
            strings = [strings]

        count = len(strings)
        # if we have no source code, ignore this shader
        if count < 1:
            raise GLSLError("No GLSL source provided.")

        # create the shader handle
        shader = glCreateShader(type)

        # convert the source strings into a ctypes pointer-to-char array,
        # and upload them.  This is deep, dark, dangerous black magick -
        # don't try stuff like this at home!
        src = (c_char_p * count)(*strings)
        glShaderSource(shader, count,
                       cast(pointer(src), POINTER(POINTER(c_char))),
                       None)

        # compile the shader
        glCompileShader(shader)

        temp = c_int(0)
        # retrieve the compile status
        glGetShaderiv(shader, GL_COMPILE_STATUS, byref(temp))

        # if compilation failed, print the log
        if not temp:
            # retrieve the log length
            glGetShaderiv(shader, GL_INFO_LOG_LENGTH, byref(temp))
            # create a buffer for the log
            buffer = create_string_buffer(temp.value)
            # retrieve the log text
            glGetShaderInfoLog(shader, temp, None, buffer)
            # print the log to the console
            raise GLSLError(buffer.value)

        self.handle = shader

class VertexShader(Shader):
    def __init__(self, source):
        Shader.__init__(self, source, type='vertex')

class FragmentShader(Shader):
    def __init__(self, source):
        Shader.__init__(self, source, type='fragment')

## Not supported yet

## class GeometryShader(Shader):
##     def __init__(self, source):
##         Shader.__init__(self, source, type='geometry')


def if_bound(f):
    """Decorator: Execute this function if and only if the shader is bound.

    """
    def execute_if_bound(self, *args, **kwargs):
        if not self.bound:
            raise GLSLError("Shader is not bound.  Cannot execute assignment.")

        f(self, *args, **kwargs)

    for attr in ["func_name", "__name__", "__dict__", "__doc__"]:
        setattr(execute_if_bound, attr, getattr(f, attr))

    return execute_if_bound

class Program(list):
    """A program contains one or more Shader.

    """
    def __init__(self, shaders):
        try:
            list.__init__(self, shaders)
        except TypeError:
            # In case only one shader was provided
            list.__init__(self, [shaders])

        self.handle = glCreateProgram()

        # source is not linked yet
        self.linked = False

        # not bound yet (i.e. not in rendering pipeline)
        self.bound = False

        self._link()

    def append(self, shader):
        """Append a Shader to the Program.

        """
        self.linked = False
        list.append(self, shader)

        if self.bound:
            self.bind()

    def _link(self):
        for shader in self:
            glAttachShader(self.handle, shader.handle);

        # link the program
        glLinkProgram(self.handle)

        temp = c_int(0)
        # retrieve the link status
        glGetProgramiv(self.handle, GL_LINK_STATUS, byref(temp))

        # if linking failed, print the log
        if not temp:
            #       retrieve the log length
            glGetProgramiv(self.handle, GL_INFO_LOG_LENGTH, byref(temp))
            # create a buffer for the log
            buffer = create_string_buffer(temp.value)
            # retrieve the log text
            glGetProgramInfoLog(self.handle, temp, None, buffer)
            # print the log to the console
            raise GLSLError(buffer.value)
        else:
            # all is well, so we are linked
            self.linked = True

    def bind(self):
        """Bind the program to the rendering pipeline.

        """
        if not self.linked:
            self._link()

        # bind the program
        glUseProgram(self.handle)
        self.bound = True

    def unbind(self):
        """Unbind all programs in use.

        """
        glUseProgram(0)
        self.bound = False

    # upload a floating point uniform
    @if_bound
    def uniformf(self, name, *vals):
        # check there are 1-4 values
        if len(vals) in range(1, 5):
            # select the correct function
            set_func = {1 : glUniform1f,
                        2 : glUniform2f,
                        3 : glUniform3f,
                        4 : glUniform4f
                        }[len(vals)]
            try:
                set_func(glGetUniformLocation(self.handle, name), *vals)
            except GLException:
                raise ValueError("Could not set float value.  Please "
                                 "ensure that 'uniformf' is only used "
                                 "to set float values.")
        else:
            raise ValueError("Can only upload 1 to 4 floats.")

    # upload an integer uniform
    @if_bound
    def uniformi(self, name, *vals):
        # check there are 1-4 values
        if len(vals) in range(1, 5):
            # select the correct function
            set_func = {1 : glUniform1i,
                        2 : glUniform2i,
                        3 : glUniform3i,
                        4 : glUniform4i
                        }[len(vals)]

            try:
                set_func(glGetUniformLocation(self.handle, name), *vals)
            except GLException:
                raise ValueError("Could not set integer value.  Please "
                                 "ensure that 'uniformi' is only used "
                                 "to set integer values.")
        else:
            raise ValueError("Can only upload 1 to 4 ints.")

    # upload a uniform matrix
    # works with matrices stored as lists,
    # as well as euclid matrices
    @if_bound
    def uniform_matrixf(self, name, mat):
        # obtian the uniform location
        loc = glGetUniformLocation(self.handle, name)
        # uplaod the 4x4 floating point matrix
        # Matrices are entered row-wise, not column-wise as in standard OpenGL
        glUniformMatrix4fv(loc, 1, True, (c_float * 16)(*mat))


    def insert(self, item):
        raise NotImplementedError

    def extend(self, item):
        raise NotImplementedError

    def pop(self, item):
        raise NotImplementedError

    def remove(self, item):
        raise NotImplementedError

    def reverse(self, item):
        raise NotImplementedError

    def sort(self, item):
        raise NotImplementedError

def default_vertex_shader():
    """Generate a pass-through VertexShader.

    """
    return VertexShader("void main(void) { gl_Position = ftransform(); }")
