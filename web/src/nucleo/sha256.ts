/**
 * SHA-256 en JavaScript puro (FIPS 180-4), para cuando el navegador no da
 * `crypto.subtle`.
 *
 * `crypto.subtle` solo existe en contextos seguros: HTTPS o localhost. Al
 * abrir la web por la red local (http://192.168…) no está, y sin esta
 * alternativa no se podrían verificar las huellas de los datos. Se prueba con
 * los vectores oficiales del NIST y comparándola con la de Node.
 *
 * Las constantes van escritas tal cual, en vez de calcularse con Math.cbrt o
 * Math.sqrt: el estándar no obliga a que Math.cbrt redondee igual en todos
 * los motores, y un bit distinto en Safari rompería todas las huellas. Un test
 * comprueba que coinciden con su definición.
 */

/** Primeros 32 bits de la parte fraccionaria de la raíz cúbica de los 64 primeros primos. */
export const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

/** Primeros 32 bits de la parte fraccionaria de la raíz cuadrada de los 8 primeros primos. */
export const H_INICIAL = new Uint32Array([
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]);

function rotar(x: number, n: number): number {
  return (x >>> n) | (x << (32 - n));
}

/** Huella SHA-256 en hexadecimal (64 caracteres en minúscula). */
export function sha256Js(datos: Uint8Array): string {
  // Relleno: un bit 1, ceros y la longitud en bits (64 bits, big-endian),
  // hasta un múltiplo de 64 bytes.
  const total = Math.ceil((datos.length + 9) / 64) * 64;
  const mensaje = new Uint8Array(total);
  mensaje.set(datos);
  mensaje[datos.length] = 0x80;
  const vista = new DataView(mensaje.buffer);
  const bits = datos.length * 8;
  vista.setUint32(total - 8, Math.floor(bits / 2 ** 32));
  vista.setUint32(total - 4, bits >>> 0);

  const h = Array.from(H_INICIAL);
  const w = new Uint32Array(64);
  for (let inicio = 0; inicio < total; inicio += 64) {
    for (let t = 0; t < 16; t++) {
      w[t] = vista.getUint32(inicio + 4 * t);
    }
    for (let t = 16; t < 64; t++) {
      const a = w[t - 15] ?? 0;
      const b = w[t - 2] ?? 0;
      const s0 = rotar(a, 7) ^ rotar(a, 18) ^ (a >>> 3);
      const s1 = rotar(b, 17) ^ rotar(b, 19) ^ (b >>> 10);
      w[t] = ((w[t - 16] ?? 0) + s0 + (w[t - 7] ?? 0) + s1) | 0;
    }
    let [a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0, hh = 0] = h;
    for (let t = 0; t < 64; t++) {
      const s1 = rotar(e, 6) ^ rotar(e, 11) ^ rotar(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (hh + s1 + ch + (K[t] ?? 0) + (w[t] ?? 0)) | 0;
      const s0 = rotar(a, 2) ^ rotar(a, 13) ^ rotar(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) | 0;
      hh = g;
      g = f;
      f = e;
      e = (d + temp1) | 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) | 0;
    }
    // Suma módulo 2^32, como entero sin signo (>>> 0).
    [a, b, c, d, e, f, g, hh].forEach((x, i) => {
      h[i] = ((h[i] ?? 0) + x) >>> 0;
    });
  }
  return h.map((x) => x.toString(16).padStart(8, "0")).join("");
}
