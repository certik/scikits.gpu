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

import pyglet.gl as gl
from ctypes import pointer, POINTER, c_char_p, byref, cast, c_char, c_int, \
                   create_string_buffer

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
        shader_type = {'vertex': gl.GL_VERTEX_SHADER,
                       'fragment': gl.GL_FRAGMENT_SHADER,}
        ##             'geometry': gl.GL_GEOMETRY_SHADER}

        if isinstance(source, basestring):
            source = [source]

        count = len(source)
        # if we have no source code, ignore this shader
        if count < 1:
            raise GLSLError("No GLSL source provided.")

        # create the shader handle
        shader = gl.glCreateShader(shader_type[type])

        # convert the source strings into a ctypes pointer-to-char array,
        # and upload them.  This is deep, dark, dangerous black magick -
        # don't try stuff like this at home!
        src = (c_char_p * count)(*source)
        gl.glShaderSource(shader, count,
                          cast(pointer(src), POINTER(POINTER(c_char))),
                       None)

        # compile the shader
        gl.glCompileShader(shader)

        temp = c_int(0)
        # retrieve the compile status
        gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS, byref(temp))

        # if compilation failed, print the log
        if not temp:
            # retrieve the log length
            gl.glGetShaderiv(shader, gl.GL_INFO_LOG_LENGTH, byref(temp))
            # create a buffer for the log
            buffer = create_string_buffer(temp.value)
            # retrieve the log text
            gl.glGetShaderInfoLog(shader, temp, None, buffer)
            # print the log to the console
            raise GLSLError(buffer.value)

        self.handle = shader
        self.source = "\n".join(source)

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

        self.handle = gl.glCreateProgram()

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
            gl.glAttachShader(self.handle, shader.handle);

        # link the program
        gl.glLinkProgram(self.handle)

        temp = c_int(0)
        # retrieve the link status
        gl.glGetProgramiv(self.handle, gl.GL_LINK_STATUS, byref(temp))

        # if linking failed, print the log
        if not temp:
            #       retrieve the log length
            gl.glGetProgramiv(self.handle, gl.GL_INFO_LOG_LENGTH, byref(temp))
            # create a buffer for the log
            buffer = create_string_buffer(temp.value)
            # retrieve the log text
            gl.glGetProgramInfoLog(self.handle, temp, None, buffer)
            # print the log to the console
            raise GLSLError(buffer.value)
        else:
            # all is well, so we are linked
            self.linked = True

    def _update_uniform_types(self):
        """Determine the numeric types of uniform variables.

        Updates the internal dictionary _uniform_type_info[var] with:

        kind : {'mat', 'vec', 'int', 'float'}
            The kind of numeric type.
        shape : {2, 3, 4}
            The shape of the type, e.g., 4 for vec4, 2 for mat2, 1 for scalar.
        array : bool
            Whether the variable is defined as an array, e.g.,
            uniform vec4 x[]; ==> true.

        """
        source = ";".join([s.source for s in self])

        # And look at each statement individually
        source = [s.strip() for s in source.split(';')]

        # Now look only at uniform declarations
        source = [s[len('uniform')+1:] for s in source if s.startswith('uniform')]

        types = [desc_name.split(' ') for desc_name in source]
        type_info = {}

        for desc, name in types:
            # Check for vector type, e.g. float x[12]
            name_array = name.split('[')
            var_name = name_array[0]

            # If array size is specified, see what it is
            if len(name_array) > 1:
                array_size = name_array[1].split(']')[0].strip()
                if not array_size:
                    raise RuntimeError("Array declaration without size is not "
                                       "supported.")

                array_size = int(array_size)
            else:
                array_size = 1

            # Check if type is, e.g., vec3
            vec_param = desc[-1]
            if vec_param.isdigit():
                shape = int(vec_param)
                desc = desc[:-1]
            else:
                shape = 1

            var_info = {
                'kind': desc,
                'shape': shape,
                'array': array_size}

            if type_info.has_key(var_name) and \
                   type_info[var_name] != var_info:
                raise GLSLError("Inconsistent definition of variable '%s'." % \
                                var_name)
            else:
                type_info[var_name] = var_info

        self._uniform_type_info = type_info

    def bind(self):
        """Bind the program to the rendering pipeline.

        """
        if not self.linked:
            self._link()

        # bind the program
        gl.glUseProgram(self.handle)
        self._update_uniform_types()
        self.bound = True

    def unbind(self):
        """Unbind all programs in use.

        """
        gl.glUseProgram(0)
        self.bound = False

    def _uniform_loc_and_storage(self, var):
        """Return the uniform location and a container that can
        store its value.

        Parameters
        ----------
        var : string
            Uniform name.

        """
        var_info = self._uniform_type_info[var]

        # If this is an array, how many values are involved?
        count = var_info['array']

        if var_info['kind'] in ['int']:
            data_type = gl.GLint
        else:
            data_type = gl.GLfloat

        loc = gl.glGetUniformLocation(self.handle, var)

        if var_info['kind'] == 'mat':
            storage = (data_type * (count * var_info['shape']**2))
        else:
            storage = (data_type * (count * var_info['shape']))

        return loc, storage

    @if_bound
    def __setitem__(self, var, value):
        """Set uniform variable value.

        Please note that matrices must be specified in row-major format.

        """
        try:
            var_info = self._uniform_type_info[var]
        except KeyError:
            raise ValueError("Uniform variable '%s' is not defined in "
                             "shader source." % var)

        count, kind, shape = [var_info[k] for k in 'array', 'kind', 'shape']

        # Ensure the value is given as a list
        try:
            value = list(value)
        except TypeError:
            value = [value]

        loc, container = self._uniform_loc_and_storage(var)

        if var_info['kind'] == 'mat':
            gl.glUniformMatrix4fv(loc, count, True, container(*value))
        else:
            if var_info['kind'] == 'int':
                type_code = 'i'
            else:
                type_code = 'f'

            # Setter function, named something like glUniform4iv
            set_func_name = 'glUniform%d%sv' % (var_info['shape'],
                                                type_code)

            set_func = getattr(gl, set_func_name)

            set_func(loc, count, container(*value))

def default_vertex_shader():
    """Generate a pass-through VertexShader.

    """
    return VertexShader("void main(void) { gl_Position = ftransform(); }")
