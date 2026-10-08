import { createHash } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Datos, sha256 } from "../src/nucleo/datos";
import { H_INICIAL, K, sha256Js } from "../src/nucleo/sha256";
import { leerDato } from "./ayuda";

const texto = (s: string) => new TextEncoder().encode(s);

describe("SHA-256 en JavaScript", () => {
  // Vectores de prueba oficiales (NIST, FIPS 180-2, apéndice B, y CAVP).
  it.each([
    ["abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"],
    ["", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
    ["abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
      "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"],
    ["abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
      "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1"],
  ])("vector oficial «%s»", (entrada, esperado) => {
    expect(sha256Js(texto(entrada))).toBe(esperado);
  });

  it("vector oficial: un millón de «a»", () => {
    expect(sha256Js(new Uint8Array(1_000_000).fill(0x61)))
      .toBe("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
  });

  it("las constantes son las de su definición (calculadas con enteros exactos)", () => {
    const primos: bigint[] = [];
    for (let n = 2n; primos.length < 64; n++) {
      if (primos.every((p) => n % p !== 0n)) primos.push(n);
    }
    // Raíz entera de orden k por bisección: exacta, sin coma flotante.
    const raiz = (x: bigint, k: bigint): bigint => {
      let bajo = 0n;
      let alto = 1n << 64n;
      while (bajo < alto) {
        const medio = (bajo + alto + 1n) / 2n;
        if (medio ** k <= x) bajo = medio;
        else alto = medio - 1n;
      }
      return bajo;
    };
    const modulo = 1n << 32n;
    // floor(frac(p^(1/3)) · 2^32) = floor((p · 2^96)^(1/3)) mod 2^32
    expect([...K].map(BigInt)).toEqual(primos.map((p) => raiz(p << 96n, 3n) % modulo));
    expect([...H_INICIAL].map(BigInt)).toEqual(primos.slice(0, 8).map((p) => raiz(p << 64n, 2n) % modulo));
  });

  it("coincide con la de Node en todas las longitudes de 0 a 300 bytes", () => {
    // Se cruzan todos los bordes del relleno (55, 56, 63, 64, 119, 120...).
    let semilla = 12345;
    const aleatorio = () => {
      semilla = (semilla * 1103515245 + 12345) % 2 ** 31;
      return semilla & 0xff;
    };
    for (let n = 0; n <= 300; n++) {
      const datos = Uint8Array.from({ length: n }, aleatorio);
      expect(sha256Js(datos), `longitud ${n}`).toBe(createHash("sha256").update(datos).digest("hex"));
    }
  });

  it("da las huellas del manifiesto en todos los ficheros de datos", () => {
    const manifiesto = JSON.parse(new TextDecoder().decode(leerDato("manifiesto.json"))) as {
      ficheros: Record<string, { sha256: string }>;
    };
    const ficheros = Object.entries(manifiesto.ficheros);
    expect(ficheros.length).toBe(20);
    for (const [ruta, { sha256: esperado }] of ficheros) {
      expect(sha256Js(new Uint8Array(leerDato(ruta))), ruta).toBe(esperado);
    }
  });
});

describe("sin crypto.subtle (web abierta por la red local, sin HTTPS)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const cargador = (ruta: string) => Promise.resolve(leerDato(ruta));

  it("sha256 da lo mismo con y sin crypto.subtle", async () => {
    const datos = leerDato("mesa-normal.json");
    const conSutil = await sha256(datos);
    vi.stubGlobal("crypto", {}); // como en http://192.168…: crypto sin subtle
    expect(await sha256(datos)).toBe(conSutil);
    vi.stubGlobal("crypto", undefined); // navegadores sin crypto en absoluto
    expect(await sha256(datos)).toBe(conSutil);
  });

  it("los datos se cargan y se verifican igual", async () => {
    vi.stubGlobal("crypto", {});
    const datos = await Datos.cargar(cargador);
    const mesa = await datos.mesa("normal");
    expect(mesa.decision.decision).toHaveLength(1320);
    const sinSenas = datos.manifiesto.tablas_equity[0];
    if (sinSenas === undefined) throw new Error("sin tabla");
    await expect(datos.equity(sinSenas)).resolves.toBeDefined();
  });

  it("un fichero alterado se sigue rechazando", async () => {
    vi.stubGlobal("crypto", {});
    const alterado = await Datos.cargar(async (ruta) => {
      const bytes = new Uint8Array(await cargador(ruta));
      if (ruta === "mesa-normal.json") bytes[bytes.length - 2] = 0x20;
      return bytes.buffer;
    });
    await expect(alterado.mesa("normal")).rejects.toThrow(/huella/);
  });

  it("si crypto.subtle existe pero falla, también se usa la alternativa", async () => {
    vi.stubGlobal("crypto", { subtle: { digest: () => Promise.reject(new Error("no disponible")) } });
    const datos = await Datos.cargar(cargador);
    await expect(datos.mesa("se-corta")).resolves.toBeDefined();
  });
});
