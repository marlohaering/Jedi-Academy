/*
===========================================================================
Browser (Emscripten + Regal) vertex array path.

The renderer feeds geometry through client-side vertex arrays (gl*Pointer on
plain memory) and glDrawElements/glDrawArrays. Regal (OpenGL 1.x on WebGL)
redirects client arrays into "shadow" buffers but never uploads their contents
for glDrawElements, so batched drawing renders nothing. The only working path
used to be one glArrayElement-style call per vertex (r_primitives 3), which
costs most of the frame time.

This layer records the client array pointers and, at draw time, streams the
used vertex range of every enabled array into a real GL buffer object and the
indices into an element buffer (as 16-bit, converting GL_QUADS to triangles).
Regal handles buffer-object arrays correctly, so this is a plain, fast
glDrawElements on WebGL.
===========================================================================
*/
#ifdef __EMSCRIPTEN__

#define WGL_ARRAYS_IMPL
#include "tr_local.h"

namespace {

enum { SLOT_VERTEX, SLOT_COLOR, SLOT_TEXCOORD0, SLOT_TEXCOORD1, SLOT_NORMAL, NUM_SLOTS };

struct ClientArray {
	qboolean	enabled;
	GLint		size;
	GLenum		type;
	GLsizei		stride;
	const void	*pointer;
	GLuint		buffer;
};

ClientArray	arrays[NUM_SLOTS];
int			clientTexUnit;		// tracked via glClientActiveTexture (0 without multitexture)
GLuint		indexBuffer;
unsigned short	*indexScratch;
int			indexScratchSize;

int TypeSize( GLenum type ) {
	switch ( type ) {
	case GL_BYTE: case GL_UNSIGNED_BYTE: return 1;
	case GL_SHORT: case GL_UNSIGNED_SHORT: return 2;
	default: return 4;	// GL_FLOAT, GL_INT, GL_UNSIGNED_INT
	}
}

int SlotForState( GLenum array ) {
	switch ( array ) {
	case GL_VERTEX_ARRAY: return SLOT_VERTEX;
	case GL_COLOR_ARRAY: return SLOT_COLOR;
	case GL_TEXTURE_COORD_ARRAY: return clientTexUnit ? SLOT_TEXCOORD1 : SLOT_TEXCOORD0;
	case GL_NORMAL_ARRAY: return SLOT_NORMAL;
	default: return -1;
	}
}

void SetPointer( int slot, GLint size, GLenum type, GLsizei stride, const void *pointer ) {
	ClientArray &a = arrays[slot];
	a.size = size;
	a.type = type;
	a.stride = stride;
	a.pointer = pointer;
}

unsigned short *Scratch( int count ) {
	if ( count > indexScratchSize ) {
		indexScratchSize = count + 1024;
		indexScratch = (unsigned short *)realloc( indexScratch, indexScratchSize * sizeof( unsigned short ) );
	}
	return indexScratch;
}

// Upload vertices [0, numVerts) of each enabled array and point GL at the buffer copies.
void BindArrays( int numVerts ) {
	for ( int slot = 0; slot < NUM_SLOTS; slot++ ) {
		ClientArray &a = arrays[slot];
		if ( !a.enabled || !a.pointer )
			continue;
		const int elemSize = a.size * TypeSize( a.type );
		const int stride = a.stride ? a.stride : elemSize;
		const int bytes = ( numVerts - 1 ) * stride + elemSize;
		if ( !a.buffer )
			glGenBuffers( 1, &a.buffer );
		glBindBuffer( GL_ARRAY_BUFFER, a.buffer );
		glBufferData( GL_ARRAY_BUFFER, bytes, a.pointer, GL_STREAM_DRAW );
		switch ( slot ) {
		case SLOT_VERTEX:	glVertexPointer( a.size, a.type, a.stride, (const void *)0 ); break;
		case SLOT_COLOR:	glColorPointer( a.size, a.type, a.stride, (const void *)0 ); break;
		case SLOT_NORMAL:	glNormalPointer( a.type, a.stride, (const void *)0 ); break;
		case SLOT_TEXCOORD0:
		case SLOT_TEXCOORD1:
			if ( qglClientActiveTextureARB )
				qglClientActiveTextureARB( slot == SLOT_TEXCOORD1 ? GL_TEXTURE1_ARB : GL_TEXTURE0_ARB );
			glTexCoordPointer( a.size, a.type, a.stride, (const void *)0 );
			if ( qglClientActiveTextureARB )
				qglClientActiveTextureARB( clientTexUnit ? GL_TEXTURE1_ARB : GL_TEXTURE0_ARB );
			break;
		}
	}
	glBindBuffer( GL_ARRAY_BUFFER, 0 );
}

void DrawIndexed( GLenum mode, const unsigned short *idx, int count ) {
	if ( !indexBuffer )
		glGenBuffers( 1, &indexBuffer );
	glBindBuffer( GL_ELEMENT_ARRAY_BUFFER, indexBuffer );
	glBufferData( GL_ELEMENT_ARRAY_BUFFER, count * sizeof( unsigned short ), idx, GL_STREAM_DRAW );
	glDrawElements( mode, count, GL_UNSIGNED_SHORT, (const void *)0 );
	glBindBuffer( GL_ELEMENT_ARRAY_BUFFER, 0 );
}

} // namespace

void WGL_VertexPointer( GLint size, GLenum type, GLsizei stride, const void *p )	{ SetPointer( SLOT_VERTEX, size, type, stride, p ); }
void WGL_ColorPointer( GLint size, GLenum type, GLsizei stride, const void *p )		{ SetPointer( SLOT_COLOR, size, type, stride, p ); }
void WGL_NormalPointer( GLenum type, GLsizei stride, const void *p )				{ SetPointer( SLOT_NORMAL, 3, type, stride, p ); }
void WGL_TexCoordPointer( GLint size, GLenum type, GLsizei stride, const void *p ) {
	SetPointer( clientTexUnit ? SLOT_TEXCOORD1 : SLOT_TEXCOORD0, size, type, stride, p );
}

void WGL_EnableClientState( GLenum array ) {
	const int slot = SlotForState( array );
	if ( slot >= 0 ) arrays[slot].enabled = qtrue;
	glEnableClientState( array );
}

void WGL_DisableClientState( GLenum array ) {
	const int slot = SlotForState( array );
	if ( slot >= 0 ) arrays[slot].enabled = qfalse;
	glDisableClientState( array );
}

void WGL_ClientActiveTexture( GLenum unit ) {
	clientTexUnit = ( unit == GL_TEXTURE1_ARB );
	if ( qglClientActiveTextureARB )
		qglClientActiveTextureARB( unit );
}

void WGL_DrawElements( GLenum mode, GLsizei count, GLenum type, const void *indices ) {
	if ( count <= 0 )
		return;
	unsigned short *idx = Scratch( count );
	int maxIndex = 0;
	if ( type == GL_UNSIGNED_SHORT ) {
		const unsigned short *in = (const unsigned short *)indices;
		for ( int i = 0; i < count; i++ ) { idx[i] = in[i]; if ( in[i] > maxIndex ) maxIndex = in[i]; }
	} else {
		const unsigned int *in = (const unsigned int *)indices;
		for ( int i = 0; i < count; i++ ) {
			if ( in[i] > 65535 ) return;	// cannot happen for tess (SHADER_MAX_VERTEXES)
			idx[i] = (unsigned short)in[i];
			if ( (int)in[i] > maxIndex ) maxIndex = in[i];
		}
	}
	BindArrays( maxIndex + 1 );
	DrawIndexed( mode, idx, count );
}

void WGL_DrawArrays( GLenum mode, GLint first, GLsizei count ) {
	if ( count <= 0 )
		return;
	if ( mode == GL_QUADS ) {	// not in WebGL: two triangles per quad
		const int quads = count / 4;
		unsigned short *idx = Scratch( quads * 6 );
		for ( int q = 0; q < quads; q++ ) {
			const int v = first + q * 4;
			idx[q*6+0] = v;   idx[q*6+1] = v+1; idx[q*6+2] = v+2;
			idx[q*6+3] = v;   idx[q*6+4] = v+2; idx[q*6+5] = v+3;
		}
		BindArrays( first + quads * 4 );
		DrawIndexed( GL_TRIANGLES, idx, quads * 6 );
		return;
	}
	unsigned short *idx = Scratch( count );
	for ( int i = 0; i < count; i++ )
		idx[i] = first + i;
	BindArrays( first + count );
	DrawIndexed( mode, idx, count );
}

#endif // __EMSCRIPTEN__
