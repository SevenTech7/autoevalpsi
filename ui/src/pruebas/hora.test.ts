import { describe, expect, it } from "vitest";

import { fechaHoraBolivia } from "../componentes/TablaEvaluaciones";

describe("fechaHoraBolivia", () => {
  it("convierte UTC a la hora de Bolivia, incluso cambiando de día", () => {
    expect(fechaHoraBolivia("2026-11-08T02:35:00+00:00")).toBe("07/11/2026 22:35");
    expect(fechaHoraBolivia("2026-11-08T02:35:00Z")).toBe("07/11/2026 22:35");
    expect(fechaHoraBolivia("2026-01-01T03:00:00+00:00")).toBe("31/12/2025 23:00");
  });

  it("una hora que ya trae la zona de Bolivia queda igual", () => {
    expect(fechaHoraBolivia("2026-11-07T22:35:00-04:00")).toBe("07/11/2026 22:35");
  });

  it("otras zonas se convierten a Bolivia", () => {
    expect(fechaHoraBolivia("2026-11-07T22:35:00+02:00")).toBe("07/11/2026 16:35");
  });

  it("sin zona se toma como hora de Bolivia", () => {
    expect(fechaHoraBolivia("2026-11-07T10:30:00")).toBe("07/11/2026 10:30");
  });

  it("lo que no es una fecha se devuelve tal cual", () => {
    expect(fechaHoraBolivia("ayer")).toBe("ayer");
  });
});
