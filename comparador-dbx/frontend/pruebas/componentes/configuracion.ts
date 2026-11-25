import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Sin `globals`, testing-library no limpia solo el DOM entre pruebas.
afterEach(cleanup);
