// Refleja backend/api/schemas.py campo por campo.
export type Tipo = "normativa" | "manual_control";
export type Marca = "A" | "L" | "R" | "X" | "P";

export interface ErrorNegocio { codigo: string; mensaje: string }

export interface Metadatos {
  entidad_emisora: string | null;
  titulo_oficial: string | null;
  libro: string | null;
  titulo: string | null;
  capitulo: string | null;
  numero_norma: string | null;
  fecha_vigencia: string | null;
}

export type EstadoDoc = "cargado" | "en_cola" | "extrayendo" | "seccionando" | "indexando" | "listo" | "error";

export interface DocumentoOut {
  id: string;
  nombre: string;
  paginas: number;
  tipo: Tipo | null;
  tipo_sugerido: boolean;
  metadatos: Metadatos;
  estado: EstadoDoc;
  advertencias: string[];
  error: ErrorNegocio | null;
}

export interface DocumentoPatch { tipo?: Tipo | null; metadatos?: Partial<Metadatos> | null }
export interface ProcesarIn { doc_ids: string[] }

export interface JobOut {
  job_id: string;
  tipo: "procesamiento" | "comparacion";
  estado: "en_cola" | "en_curso" | "listo" | "error";
  etapa: string;
  doc_actual: string;
  progreso: number;
  mensaje: string;
  errores: ErrorNegocio[];
  documentos: Record<string, string>;
  comparacion_id: string | null;
}

export interface NodoOut {
  id: string;
  identificador: string;
  titulo: string;
  preview: string;
  hoja: boolean;
  incierto: boolean;
  excluida: boolean;
  motivo: string;
  seleccionada: boolean;
  pagina_inicio: number;
  hijos: NodoOut[];
}

export interface ArbolDocOut { doc_id: string; nombre: string; nodos: NodoOut[]; avisos: string[] }

export interface SeccionOut {
  id: string;
  doc_nombre: string;
  identificador: string;
  titulo: string;
  ruta: string[];
  texto: string;
  pagina_inicio: number;
  pagina_fin: number;
  incierto: boolean;
}

export interface ComparacionIn { articulo_ids: string[]; seccion_ids: string[] }

export interface FilaVia1 {
  articulo_id: string;
  documento: string;
  identificador: string;
  ruta: string;
  texto_articulo: string;
  marca: Marca;
  comentario: string;
  cita_norma: string;
  cita_manual: string;
  seccion_respaldo_id: string | null;
  seccion_respaldo: string;
  confianza: number | null;
  requiere_revision: boolean;
  elementos_faltantes: string[];
}

export interface ParVia2 { articulo_id: string; identificador: string; cobertura: "total" | "parcial" | "nula" }

export interface FilaVia2 {
  seccion_id: string;
  identificador: string;
  titulo: string;
  sin_base: boolean;
  pares: ParVia2[];
}

export interface ComparacionOut {
  id: string;
  estado: "en_curso" | "listo" | "error";
  conteos: Record<string, number>;
  via1: FilaVia1[];
  via2: FilaVia2[];
  conclusion: string;
  conclusion_editada: boolean;
  pares_juzgados: number;
  pares_a_revision: number;
  avisos: string[];
}

export interface SesionOut { documentos: DocumentoOut[]; comparacion_id: string | null }
export interface HealthOut { estado: "ok" | "degradado"; stage: string; llm: boolean; mensaje: string }
