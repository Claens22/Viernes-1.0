import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "viernes.db"

VIERNES_URL = "http://127.0.0.1:8081/v1/chat/completions"
SYSTEM_PROMPT_PATH = BASE_DIR.parent / "viernes-system.txt"

INTERVALO_CONTROL = 5

API_HOST = "127.0.0.1"
API_PORT = 8090

TIMEOUT_VIERNES = 180

MAX_REINTENTOS = 3

ESTADOS_VIERNES = {
    "ANALIZADO",
    "DUDOSO",
    "NO_SABE",
    "FALLO"
}

ESTADOS_USUARIO = {
    "VERIFICADO",
    "ERRONEO",
    "DESCARTADO",
    "REVISAR"
}

ESTADOS_TAREA = {
    "PENDIENTE",
    "PROCESSING",
    "ANALIZADO",
    "REVISION",
    "FALLO",
    "VERIFICADO",
    "ERRONEO",
    "DESCARTADO"
}


def ahora():
    return datetime.now().isoformat(timespec="seconds")


class Controlador:

    def __init__(
        self,
        db_path=DB_PATH,
        viernes_url=VIERNES_URL,
        system_prompt_path=SYSTEM_PROMPT_PATH
    ):
        self.db_path = db_path
        self.viernes_url = viernes_url
        self.system_prompt_path = system_prompt_path
        self._detener = threading.Event()

        self._crear_bd()
        self._migrar_bd()
        self._recuperar_tareas_interrumpidas()

    # =========================================================
    # BASE DE DATOS
    # =========================================================

    def _conexion(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=10
        )

        conn.row_factory = sqlite3.Row

        conn.execute(
            "PRAGMA foreign_keys = ON"
        )

        conn.execute(
            "PRAGMA busy_timeout = 10000"
        )

        return conn

    def _crear_bd(self):
        with self._conexion() as conn:

            conn.execute(
                "PRAGMA journal_mode = WAL"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS bruta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT NOT NULL,
                    contenido TEXT NOT NULL,
                    origen TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS tareas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_creacion TEXT NOT NULL,
                    origen_bruta_id INTEGER,
                    contenido TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    intentos INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (origen_bruta_id)
                        REFERENCES bruta(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS resultados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarea_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    estado_viernes TEXT NOT NULL,
                    respuesta TEXT,
                    motivo TEXT,
                    FOREIGN KEY (tarea_id)
                        REFERENCES tareas(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS verificacion (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarea_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    estado_usuario TEXT NOT NULL,
                    comentario TEXT,
                    contenido_verificado TEXT,
                    FOREIGN KEY (tarea_id)
                        REFERENCES tareas(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS conocimiento (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT NOT NULL,
                    origen_tarea_id INTEGER,
                    contenido TEXT NOT NULL,
                    fuente TEXT,
                    estado TEXT NOT NULL DEFAULT 'ACTIVO',
                    FOREIGN KEY (origen_tarea_id)
                        REFERENCES tareas(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS revision (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarea_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    motivo TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                    comentario TEXT,
                    FOREIGN KEY (tarea_id)
                        REFERENCES tareas(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS errores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarea_id INTEGER,
                    fecha TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    detalle TEXT NOT NULL,
                    FOREIGN KEY (tarea_id)
                        REFERENCES tareas(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT NOT NULL,
                    tarea_id INTEGER,
                    rol TEXT NOT NULL,
                    contenido TEXT NOT NULL,
                    FOREIGN KEY (tarea_id)
                        REFERENCES tareas(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS eventos_controlador (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    tarea_id INTEGER,
                    detalle TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS estado_servicio (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    estado TEXT NOT NULL,
                    fecha TEXT NOT NULL,
                    detalle TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tareas_estado
                ON tareas(estado)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_resultados_tarea
                ON resultados(tarea_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_revision_estado
                ON revision(estado)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_errores_tarea
                ON errores(tarea_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_eventos_tarea
                ON eventos_controlador(tarea_id)
            """)

    def _migrar_bd(self):
        """
        Actualizaciones de estructura para bases de datos
        creadas con versiones anteriores del controlador.
        No borra datos.
        """

        with self._conexion() as conn:

            columnas = conn.execute("""
                PRAGMA table_info(verificacion)
            """).fetchall()

            nombres = {
                columna["name"]
                for columna in columnas
            }

            if "contenido_verificado" not in nombres:

                conn.execute("""
                    ALTER TABLE verificacion
                    ADD COLUMN contenido_verificado TEXT
                """)

    def _evento(
        self,
        conn,
        tipo,
        tarea_id=None,
        detalle=None
    ):
        if isinstance(detalle, (dict, list)):
            detalle = json.dumps(
                detalle,
                ensure_ascii=False
            )

        conn.execute("""
            INSERT INTO eventos_controlador (
                fecha,
                tipo,
                tarea_id,
                detalle
            )
            VALUES (?, ?, ?, ?)
        """, (
            ahora(),
            tipo,
            tarea_id,
            detalle
        ))

    def _estado_servicio(
        self,
        estado,
        detalle=None
    ):
        with self._conexion() as conn:

            conn.execute("""
                INSERT INTO estado_servicio (
                    id,
                    estado,
                    fecha,
                    detalle
                )
                VALUES (
                    1,
                    ?,
                    ?,
                    ?
                )
                ON CONFLICT(id)
                DO UPDATE SET
                    estado = excluded.estado,
                    fecha = excluded.fecha,
                    detalle = excluded.detalle
            """, (
                estado,
                ahora(),
                detalle
            ))

    def _recuperar_tareas_interrumpidas(self):

        with self._conexion() as conn:

            filas = conn.execute("""
                SELECT id
                FROM tareas
                WHERE estado = 'PROCESSING'
            """).fetchall()

            for fila in filas:

                tarea_id = fila["id"]

                conn.execute("""
                    UPDATE tareas
                    SET estado = 'PENDIENTE'
                    WHERE id = ?
                """, (
                    tarea_id,
                ))

                conn.execute("""
                    INSERT INTO errores (
                        tarea_id,
                        fecha,
                        tipo,
                        detalle
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    tarea_id,
                    ahora(),
                    "CONTROLADOR_REINICIADO",
                    "La tarea estaba en PROCESSING cuando "
                    "el controlador se inició nuevamente."
                ))

                self._evento(
                    conn,
                    "TAREA_RECUPERADA",
                    tarea_id,
                    "Tarea devuelta a PENDIENTE tras reinicio."
                )

            conn.execute("""
                INSERT INTO estado_servicio (
                    id,
                    estado,
                    fecha,
                    detalle
                )
                VALUES (
                    1,
                    'INICIANDO',
                    ?,
                    ?
                )
                ON CONFLICT(id)
                DO UPDATE SET
                    estado = excluded.estado,
                    fecha = excluded.fecha,
                    detalle = excluded.detalle
            """, (
                ahora(),
                "Controlador iniciado."
            ))

    # =========================================================
    # BRUTA -> TAREAS
    # =========================================================

    def crear_tarea_desde_bruta(
        self,
        bruta_id
    ):

        with self._conexion() as conn:

            fila = conn.execute("""
                SELECT
                    id,
                    contenido
                FROM bruta
                WHERE id = ?
            """, (
                bruta_id,
            )).fetchone()

            if fila is None:
                raise ValueError(
                    f"No existe el registro BRUTA {bruta_id}"
                )

            existente = conn.execute("""
                SELECT id
                FROM tareas
                WHERE origen_bruta_id = ?
            """, (
                bruta_id,
            )).fetchone()

            if existente:
                return existente["id"]

            cursor = conn.execute("""
                INSERT INTO tareas (
                    fecha_creacion,
                    origen_bruta_id,
                    contenido,
                    estado,
                    intentos
                )
                VALUES (
                    ?,
                    ?,
                    ?,
                    'PENDIENTE',
                    0
                )
            """, (
                ahora(),
                bruta_id,
                fila["contenido"]
            ))

            tarea_id = cursor.lastrowid

            self._evento(
                conn,
                "TAREA_CREADA_DESDE_BRUTA",
                tarea_id,
                f"BRUTA {bruta_id}"
            )

            return tarea_id

    def crear_tareas_pendientes_desde_bruta(self):

        creadas = []

        with self._conexion() as conn:

            filas = conn.execute("""
                SELECT
                    b.id,
                    b.contenido
                FROM bruta b
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM tareas t
                    WHERE t.origen_bruta_id = b.id
                )
                ORDER BY b.id ASC
            """).fetchall()

            for fila in filas:

                cursor = conn.execute("""
                    INSERT INTO tareas (
                        fecha_creacion,
                        origen_bruta_id,
                        contenido,
                        estado,
                        intentos
                    )
                    VALUES (
                        ?,
                        ?,
                        ?,
                        'PENDIENTE',
                        0
                    )
                """, (
                    ahora(),
                    fila["id"],
                    fila["contenido"]
                ))

                tarea_id = cursor.lastrowid

                creadas.append(tarea_id)

                self._evento(
                    conn,
                    "TAREA_CREADA_DESDE_BRUTA",
                    tarea_id,
                    f"BRUTA {fila['id']}"
                )

        return creadas

    def listar_bruta(
        self,
        limite=100
    ):

        with self._conexion() as conn:

            filas = conn.execute("""
                SELECT
                    id,
                    fecha,
                    contenido,
                    origen
                FROM bruta
                ORDER BY id ASC
                LIMIT ?
            """, (
                limite,
            )).fetchall()

            return [
                dict(fila)
                for fila in filas
            ]

    # =========================================================
    # COLA
    # =========================================================

    def obtener_siguiente_tarea_pendiente(self):

        with self._conexion() as conn:

            fila = conn.execute("""
                SELECT
                    id,
                    contenido
                FROM tareas
                WHERE estado = 'PENDIENTE'
                ORDER BY id ASC
                LIMIT 1
            """).fetchone()

            if fila is None:
                return None

            tarea_id = fila["id"]

            cursor = conn.execute("""
                UPDATE tareas
                SET estado = 'PROCESSING'
                WHERE id = ?
                  AND estado = 'PENDIENTE'
            """, (
                tarea_id,
            ))

            if cursor.rowcount != 1:
                return None

            self._evento(
                conn,
                "TAREA_INICIADA",
                tarea_id,
                "Tarea tomada por la cola."
            )

            return {
                "id": tarea_id,
                "tarea": fila["contenido"]
            }

    def preparar_peticion_viernes(
        self,
        tarea_id
    ):

        with self._conexion() as conn:

            fila = conn.execute("""
                SELECT
                    id,
                    contenido,
                    estado,
                    intentos
                FROM tareas
                WHERE id = ?
            """, (
                tarea_id,
            )).fetchone()

            if fila is None:
                raise ValueError(
                    f"No existe la tarea {tarea_id}"
                )

            if fila["estado"] != "PROCESSING":
                raise ValueError(
                    f"La tarea {tarea_id} "
                    "no está en PROCESSING"
                )

            nuevo_intento = fila["intentos"] + 1

            conn.execute("""
                UPDATE tareas
                SET intentos = ?
                WHERE id = ?
            """, (
                nuevo_intento,
                tarea_id
            ))

            self._evento(
                conn,
                "INTENTO_VIERNES",
                tarea_id,
                f"Intento {nuevo_intento}"
            )

            return {
                "id": fila["id"],
                "tarea": fila["contenido"],
                "intento": nuevo_intento
            }

    # =========================================================
    # VIERNES
    # =========================================================

    def _leer_system_prompt(self):

        if not self.system_prompt_path.exists():
            raise FileNotFoundError(
                "No existe el system prompt: "
                f"{self.system_prompt_path}"
            )

        return self.system_prompt_path.read_text(
            encoding="utf-8"
        )

    def chat_directo(
        self,
        mensajes
    ):
        """
        Envía una conversación normal a Viernes.
        No crea ni modifica tareas de la cola.
        """

        system_prompt = self._leer_system_prompt()

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        messages.extend(mensajes)

        body = {
            "messages": messages,
            "temperature": 0
        }

        datos = json.dumps(
            body,
            ensure_ascii=False
        ).encode("utf-8")

        solicitud = urllib.request.Request(
            self.viernes_url,
            data=datos,
            headers={
                "Content-Type":
                    "application/json; charset=utf-8"
            },
            method="POST"
        )

        with urllib.request.urlopen(
            solicitud,
            timeout=TIMEOUT_VIERNES
        ) as respuesta_http:

            contenido = (
                respuesta_http
                .read()
                .decode("utf-8")
            )

        datos_respuesta = json.loads(
            contenido
        )

        respuesta = (
            datos_respuesta
            ["choices"][0]
            ["message"]
            ["content"]
        )

        return respuesta

    def _crear_esquema_respuesta(self):

        return {
            "type": "object",
            "properties": {
                "estado": {
                    "type": "string",
                    "enum": [
                        "ANALIZADO",
                        "DUDOSO",
                        "NO_SABE"
                    ]
                },
                "respuesta": {
                    "type": "string"
                },
                "motivo": {
                    "type": "string"
                }
            },
            "required": [
                "estado",
                "respuesta",
                "motivo"
            ],
            "additionalProperties": False
        }

    def enviar_tarea_a_viernes(
        self,
        tarea_id
    ):

        peticion = self.preparar_peticion_viernes(
            tarea_id
        )

        try:

            system_prompt = self._leer_system_prompt()

            body = {
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": peticion["tarea"]
                    }
                ],
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "respuesta_viernes",
                        "strict": True,
                        "schema":
                            self._crear_esquema_respuesta()
                    }
                }
            }

            datos = json.dumps(
                body,
                ensure_ascii=False
            ).encode("utf-8")

            solicitud = urllib.request.Request(
                self.viernes_url,
                data=datos,
                headers={
                    "Content-Type":
                        "application/json; charset=utf-8"
                },
                method="POST"
            )

            self._estado_servicio(
                "PROCESSING",
                f"Tarea {tarea_id} en Viernes."
            )

            with urllib.request.urlopen(
                solicitud,
                timeout=TIMEOUT_VIERNES
            ) as respuesta_http:

                contenido = (
                    respuesta_http
                    .read()
                    .decode("utf-8")
                )

            datos_respuesta = json.loads(
                contenido
            )

            contenido_viernes = (
                datos_respuesta
                ["choices"][0]
                ["message"]
                ["content"]
            )

            resultado = json.loads(
                contenido_viernes
            )

            estado = resultado.get(
                "estado"
            )

            respuesta = resultado.get(
                "respuesta",
                ""
            )

            motivo = resultado.get(
                "motivo",
                ""
            )

            if estado not in {
                "ANALIZADO",
                "DUDOSO",
                "NO_SABE"
            }:
                raise ValueError(
                    "Respuesta de Viernes inválida: "
                    f"{resultado}"
                )

            self.recibir_respuesta({
                "id": peticion["id"],
                "estado": estado,
                "respuesta": respuesta,
                "motivo": motivo
            })

            self._estado_servicio(
                "DISPONIBLE",
                f"Última tarea completada: {tarea_id}"
            )

            return resultado

        except Exception as error:

            motivo = (
                "Fallo técnico al comunicarse con "
                f"llama-server: {error}"
            )

            resultado = {
                "estado": "FALLO",
                "respuesta": "",
                "motivo": motivo
            }

            self._registrar_fallo_tarea(
                tarea_id,
                "FALLO_VIERNES",
                motivo
            )

            return resultado

    # =========================================================
    # RESULTADOS / FALLOS
    # =========================================================

    def _registrar_fallo_tarea(
        self,
        tarea_id,
        tipo,
        detalle
    ):

        with self._conexion() as conn:

            tarea = conn.execute("""
                SELECT
                    intentos,
                    estado
                FROM tareas
                WHERE id = ?
            """, (
                tarea_id,
            )).fetchone()

            if tarea is None:
                return

            fecha = ahora()

            conn.execute("""
                INSERT INTO resultados (
                    tarea_id,
                    fecha,
                    estado_viernes,
                    respuesta,
                    motivo
                )
                VALUES (
                    ?,
                    ?,
                    'FALLO',
                    '',
                    ?
                )
            """, (
                tarea_id,
                fecha,
                detalle
            ))

            conn.execute("""
                INSERT INTO errores (
                    tarea_id,
                    fecha,
                    tipo,
                    detalle
                )
                VALUES (?, ?, ?, ?)
            """, (
                tarea_id,
                fecha,
                tipo,
                detalle
            ))

            if tarea["intentos"] < MAX_REINTENTOS:

                nuevo_estado = "PENDIENTE"

                detalle_evento = (
                    "Fallo registrado. "
                    "Se reintentará. "
                    f"Intento {tarea['intentos']} "
                    f"de {MAX_REINTENTOS}."
                )

            else:

                nuevo_estado = "REVISION"

                conn.execute("""
                    INSERT INTO revision (
                        tarea_id,
                        fecha,
                        motivo,
                        estado
                    )
                    VALUES (
                        ?,
                        ?,
                        ?,
                        'PENDIENTE'
                    )
                """, (
                    tarea_id,
                    fecha,
                    "Se alcanzó el máximo de "
                    "reintentos por fallo técnico."
                ))

                detalle_evento = (
                    "Máximo de reintentos alcanzado. "
                    "Tarea enviada a REVISION."
                )

            conn.execute("""
                UPDATE tareas
                SET estado = ?
                WHERE id = ?
            """, (
                nuevo_estado,
                tarea_id
            ))

            self._evento(
                conn,
                "FALLO_TAREA",
                tarea_id,
                detalle_evento
            )

    def recibir_respuesta(
        self,
        respuesta
    ):

        campos = {
            "id",
            "estado",
            "respuesta",
            "motivo"
        }

        if not campos.issubset(respuesta):

            raise ValueError(
                "La respuesta de Viernes no contiene "
                "todos los campos obligatorios."
            )

        tarea_id = respuesta["id"]
        estado = respuesta["estado"]
        texto = respuesta["respuesta"]
        motivo = respuesta["motivo"]

        if estado not in {
            "ANALIZADO",
            "DUDOSO",
            "NO_SABE"
        }:
            raise ValueError(
                f"Estado de Viernes no válido: {estado}"
            )

        with self._conexion() as conn:

            tarea = conn.execute("""
                SELECT
                    id,
                    estado
                FROM tareas
                WHERE id = ?
            """, (
                tarea_id,
            )).fetchone()

            if tarea is None:
                raise ValueError(
                    "Viernes devolvió un ID inexistente: "
                    f"{tarea_id}"
                )

            if tarea["estado"] != "PROCESSING":
                raise ValueError(
                    f"La tarea {tarea_id} "
                    "ya no está en PROCESSING."
                )

            fecha = ahora()

            conn.execute("""
                INSERT INTO resultados (
                    tarea_id,
                    fecha,
                    estado_viernes,
                    respuesta,
                    motivo
                )
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
            """, (
                tarea_id,
                fecha,
                estado,
                texto,
                motivo
            ))

            if estado == "ANALIZADO":
                nuevo_estado = "ANALIZADO"
            else:
                nuevo_estado = "REVISION"

            conn.execute("""
                UPDATE tareas
                SET estado = ?
                WHERE id = ?
            """, (
                nuevo_estado,
                tarea_id
            ))

            if estado in {
                "DUDOSO",
                "NO_SABE"
            }:

                conn.execute("""
                    INSERT INTO revision (
                        tarea_id,
                        fecha,
                        motivo,
                        estado
                    )
                    VALUES (
                        ?,
                        ?,
                        ?,
                        'PENDIENTE'
                    )
                """, (
                    tarea_id,
                    fecha,
                    motivo
                ))

            self._evento(
                conn,
                f"RESPUESTA_{estado}",
                tarea_id,
                motivo
            )

    # =========================================================
    # VERIFICACIÓN HUMANA
    # =========================================================

    def verificar_tarea(
        self,
        tarea_id,
        estado,
        comentario="",
        contenido_verificado=""
    ):

        estado = (estado or "").strip().upper()
        comentario = comentario or ""
        contenido_verificado = contenido_verificado or ""

        if estado not in ESTADOS_USUARIO:
            raise ValueError(
                f"Estado de usuario no válido: {estado}. "
                f"Permitidos: {sorted(ESTADOS_USUARIO)}"
            )

        with self._conexion() as conn:

            tarea = conn.execute("""
                SELECT *
                FROM tareas
                WHERE id = ?
            """, (
                tarea_id,
            )).fetchone()

            if tarea is None:
                raise ValueError(
                    f"No existe la tarea {tarea_id}."
                )

            fecha = ahora()

            # -------------------------------------------------
            # 1. Registrar siempre la verificación humana
            # -------------------------------------------------

            conn.execute("""
                INSERT INTO verificacion (
                    tarea_id,
                    fecha,
                    estado_usuario,
                    comentario,
                    contenido_verificado
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                tarea_id,
                fecha,
                estado,
                comentario,
                contenido_verificado
            ))

            # -------------------------------------------------
            # 2. VERIFICADO
            # -------------------------------------------------

            if estado == "VERIFICADO":

                contenido = contenido_verificado.strip()

                origen_contenido = "usuario"

                # Si el usuario no proporciona contenido
                # explícitamente, utilizamos la última respuesta
                # válida de Viernes.
                if not contenido:

                    resultado = conn.execute("""
                        SELECT
                            respuesta,
                            estado_viernes
                        FROM resultados
                        WHERE tarea_id = ?
                          AND estado_viernes IN (
                              'ANALIZADO',
                              'DUDOSO',
                              'NO_SABE'
                          )
                          AND TRIM(
                              COALESCE(respuesta, '')
                          ) <> ''
                        ORDER BY id DESC
                        LIMIT 1
                    """, (
                        tarea_id,
                    )).fetchone()

                    if resultado is not None:

                        contenido = (
                            resultado["respuesta"] or ""
                        ).strip()

                        origen_contenido = (
                            "resultado_viernes"
                        )

                # ---------------------------------------------
                # 3. Guardar conocimiento verificado
                # ---------------------------------------------

                if contenido:

                    # Desactivamos conocimiento anterior
                    # de esta misma tarea, conservando
                    # el historial.
                    conn.execute("""
                        UPDATE conocimiento
                        SET estado = 'INACTIVO'
                        WHERE origen_tarea_id = ?
                          AND estado = 'ACTIVO'
                    """, (
                        tarea_id,
                    ))

                    conn.execute("""
                        INSERT INTO conocimiento (
                            fecha,
                            origen_tarea_id,
                            contenido,
                            fuente,
                            estado
                        )
                        VALUES (?, ?, ?, ?, 'ACTIVO')
                    """, (
                        fecha,
                        tarea_id,
                        contenido,
                        origen_contenido
                    ))

                    self._evento(
                        conn,
                        "CONOCIMIENTO_VERIFICADO",
                        tarea_id,
                        {
                            "estado": estado,
                            "contenido_origen":
                                origen_contenido
                        }
                    )

                else:

                    self._evento(
                        conn,
                        "VERIFICACION_SIN_CONTENIDO",
                        tarea_id,
                        {
                            "estado": estado,
                            "comentario": comentario
                        }
                    )

                # La tarea queda verificada.
                # La tabla actual no dispone de
                # fecha_actualizacion, por lo que no se
                # modifica una columna inexistente.
                conn.execute("""
                    UPDATE tareas
                    SET estado = 'VERIFICADO'
                    WHERE id = ?
                """, (
                    tarea_id,
                ))

            # -------------------------------------------------
            # 4. ERRONEO / DESCARTADO
            # -------------------------------------------------

            elif estado in {
                "ERRONEO",
                "DESCARTADO"
            }:

                conn.execute("""
                    UPDATE conocimiento
                    SET estado = 'INACTIVO'
                    WHERE origen_tarea_id = ?
                      AND estado = 'ACTIVO'
                """, (
                    tarea_id,
                ))

                conn.execute("""
                    UPDATE tareas
                    SET estado = ?
                    WHERE id = ?
                """, (
                    estado,
                    tarea_id
                ))

                self._evento(
                    conn,
                    f"VERIFICACION_{estado}",
                    tarea_id,
                    {
                        "comentario": comentario
                    }
                )

            # -------------------------------------------------
            # 5. REVISAR
            # -------------------------------------------------

            elif estado == "REVISAR":

                conn.execute("""
                    UPDATE tareas
                    SET estado = 'REVISION'
                    WHERE id = ?
                """, (
                    tarea_id,
                ))

                revision = conn.execute("""
                    SELECT id
                    FROM revision
                    WHERE tarea_id = ?
                      AND estado = 'PENDIENTE'
                    LIMIT 1
                """, (
                    tarea_id,
                )).fetchone()

                if revision is None:

                    conn.execute("""
                        INSERT INTO revision (
                            tarea_id,
                            fecha,
                            motivo,
                            estado,
                            comentario
                        )
                        VALUES (
                            ?,
                            ?,
                            ?,
                            'PENDIENTE',
                            ?
                        )
                    """, (
                        tarea_id,
                        fecha,
                        comentario or
                            "Revisión solicitada por el usuario.",
                        comentario
                    ))

                self._evento(
                    conn,
                    "VERIFICACION_REVISAR",
                    tarea_id,
                    {
                        "comentario": comentario
                    }
                )

            # -------------------------------------------------
            # 6. Evento final
            # -------------------------------------------------

            self._evento(
                conn,
                f"VERIFICACION_{estado}",
                tarea_id,
                {
                    "comentario": comentario
                }
            )

            return {
                "ok": True,
                "tarea_id": tarea_id,
                "estado": estado,
                "contenido_verificado":
                    contenido_verificado
            }

    # =========================================================
    # CONOCIMIENTO
    # =========================================================

    def listar_conocimiento(
        self,
        estado="ACTIVO",
        limite=100
    ):

        with self._conexion() as conn:

            if estado:

                filas = conn.execute("""
                    SELECT
                        id,
                        fecha,
                        origen_tarea_id,
                        contenido,
                        fuente,
                        estado
                    FROM conocimiento
                    WHERE estado = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    estado,
                    limite
                )).fetchall()

            else:

                filas = conn.execute("""
                    SELECT
                        id,
                        fecha,
                        origen_tarea_id,
                        contenido,
                        fuente,
                        estado
                    FROM conocimiento
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    limite,
                )).fetchall()

            return [
                dict(fila)
                for fila in filas
            ]

    def obtener_conocimiento(
        self,
        conocimiento_id
    ):

        with self._conexion() as conn:

            fila = conn.execute("""
                SELECT
                    id,
                    fecha,
                    origen_tarea_id,
                    contenido,
                    fuente,
                    estado
                FROM conocimiento
                WHERE id = ?
            """, (
                conocimiento_id,
            )).fetchone()

            if fila is None:
                return None

            return dict(fila)

    # =========================================================
    # CONVERSACIONES
    # =========================================================

    def registrar_conversacion(
        self,
        rol,
        contenido,
        tarea_id=None
    ):

        if rol not in {
            "usuario",
            "viernes",
            "sistema",
            "controlador"
        }:
            raise ValueError(
                f"Rol de conversación no válido: {rol}"
            )

        with self._conexion() as conn:

            cursor = conn.execute("""
                INSERT INTO conversaciones (
                    fecha,
                    tarea_id,
                    rol,
                    contenido
                )
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?
                )
            """, (
                ahora(),
                tarea_id,
                rol,
                contenido
            ))

            return cursor.lastrowid

    def listar_conversacion(
        self,
        tarea_id,
        limite=100
    ):

        with self._conexion() as conn:

            filas = conn.execute("""
                SELECT
                    id,
                    fecha,
                    tarea_id,
                    rol,
                    contenido
                FROM conversaciones
                WHERE tarea_id = ?
                ORDER BY id ASC
                LIMIT ?
            """, (
                tarea_id,
                limite
            )).fetchall()

            return [
                dict(fila)
                for fila in filas
            ]

    def crear_tarea_manual(
        self,
        contenido
    ):

        if not contenido or not contenido.strip():
            raise ValueError(
                "La tarea manual no puede estar vacía."
            )

        contenido = contenido.strip()

        with self._conexion() as conn:

            fecha = ahora()

            cursor = conn.execute("""
                INSERT INTO tareas (
                    fecha_creacion,
                    origen_bruta_id,
                    contenido,
                    estado,
                    intentos
                )
                VALUES (
                    ?,
                    NULL,
                    ?,
                    'PENDIENTE',
                    0
                )
            """, (
                fecha,
                contenido
            ))

            tarea_id = cursor.lastrowid

            conn.execute("""
                INSERT INTO conversaciones (
                    fecha,
                    tarea_id,
                    rol,
                    contenido
                )
                VALUES (
                    ?,
                    ?,
                    'usuario',
                    ?
                )
            """, (
                fecha,
                tarea_id,
                contenido
            ))

            self._evento(
                conn,
                "TAREA_MANUAL_CREADA",
                tarea_id,
                "Tarea creada mediante API."
            )

            return tarea_id

    # =========================================================
    # CONSULTAS
    # =========================================================

    def mostrar_tarea(
        self,
        tarea_id
    ):

        with self._conexion() as conn:

            tarea = conn.execute("""
                SELECT
                    id,
                    fecha_creacion,
                    origen_bruta_id,
                    contenido,
                    estado,
                    intentos
                FROM tareas
                WHERE id = ?
            """, (
                tarea_id,
            )).fetchone()

            if tarea is None:
                return None

            resultados = conn.execute("""
                SELECT
                    id,
                    fecha,
                    estado_viernes,
                    respuesta,
                    motivo
                FROM resultados
                WHERE tarea_id = ?
                ORDER BY id ASC
            """, (
                tarea_id,
            )).fetchall()

            verificaciones = conn.execute("""
                SELECT
                    id,
                    fecha,
                    estado_usuario,
                    comentario,
                    contenido_verificado
                FROM verificacion
                WHERE tarea_id = ?
                ORDER BY id ASC
            """, (
                tarea_id,
            )).fetchall()

            revisiones = conn.execute("""
                SELECT
                    id,
                    fecha,
                    motivo,
                    estado,
                    comentario
                FROM revision
                WHERE tarea_id = ?
                ORDER BY id ASC
            """, (
                tarea_id,
            )).fetchall()

            errores = conn.execute("""
                SELECT
                    id,
                    fecha,
                    tipo,
                    detalle
                FROM errores
                WHERE tarea_id = ?
                ORDER BY id ASC
            """, (
                tarea_id,
            )).fetchall()

            conversaciones = conn.execute("""
                SELECT
                    id,
                    fecha,
                    rol,
                    contenido
                FROM conversaciones
                WHERE tarea_id = ?
                ORDER BY id ASC
            """, (
                tarea_id,
            )).fetchall()

            eventos = conn.execute("""
                SELECT
                    id,
                    fecha,
                    tipo,
                    detalle
                FROM eventos_controlador
                WHERE tarea_id = ?
                ORDER BY id ASC
            """, (
                tarea_id,
            )).fetchall()

            return {
                "tarea": dict(tarea),
                "resultados": [
                    dict(fila)
                    for fila in resultados
                ],
                "verificaciones": [
                    dict(fila)
                    for fila in verificaciones
                ],
                "revisiones": [
                    dict(fila)
                    for fila in revisiones
                ],
                "errores": [
                    dict(fila)
                    for fila in errores
                ],
                "conversaciones": [
                    dict(fila)
                    for fila in conversaciones
                ],
                "eventos": [
                    dict(fila)
                    for fila in eventos
                ]
            }

    def listar_tareas(
        self,
        estado=None,
        limite=100
    ):

        with self._conexion() as conn:

            if estado:

                filas = conn.execute("""
                    SELECT
                        id,
                        fecha_creacion,
                        origen_bruta_id,
                        contenido,
                        estado,
                        intentos
                    FROM tareas
                    WHERE estado = ?
                    ORDER BY id ASC
                    LIMIT ?
                """, (
                    estado,
                    limite
                )).fetchall()

            else:

                filas = conn.execute("""
                    SELECT
                        id,
                        fecha_creacion,
                        origen_bruta_id,
                        contenido,
                        estado,
                        intentos
                    FROM tareas
                    ORDER BY id ASC
                    LIMIT ?
                """, (
                    limite,
                )).fetchall()

            return [
                dict(fila)
                for fila in filas
            ]

    def listar_revision(
        self,
        estado="PENDIENTE",
        limite=100
    ):

        with self._conexion() as conn:

            if estado:

                filas = conn.execute("""
                    SELECT
                        r.id,
                        r.tarea_id,
                        r.fecha,
                        r.motivo,
                        r.estado,
                        r.comentario,
                        t.contenido
                    FROM revision r
                    JOIN tareas t
                        ON t.id = r.tarea_id
                    WHERE r.estado = ?
                    ORDER BY r.id ASC
                    LIMIT ?
                """, (
                    estado,
                    limite
                )).fetchall()

            else:

                filas = conn.execute("""
                    SELECT
                        r.id,
                        r.tarea_id,
                        r.fecha,
                        r.motivo,
                        r.estado,
                        r.comentario,
                        t.contenido
                    FROM revision r
                    JOIN tareas t
                        ON t.id = r.tarea_id
                    ORDER BY r.id ASC
                    LIMIT ?
                """, (
                    limite,
                )).fetchall()

            return [
                dict(fila)
                for fila in filas
            ]

    def listar_errores(
        self,
        tarea_id=None,
        limite=100
    ):

        with self._conexion() as conn:

            if tarea_id is not None:

                filas = conn.execute("""
                    SELECT
                        id,
                        tarea_id,
                        fecha,
                        tipo,
                        detalle
                    FROM errores
                    WHERE tarea_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    tarea_id,
                    limite
                )).fetchall()

            else:

                filas = conn.execute("""
                    SELECT
                        id,
                        tarea_id,
                        fecha,
                        tipo,
                        detalle
                    FROM errores
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    limite,
                )).fetchall()

            return [
                dict(fila)
                for fila in filas
            ]

    def obtener_estado(self):

        with self._conexion() as conn:

            filas = conn.execute("""
                SELECT
                    estado,
                    COUNT(*) AS cantidad
                FROM tareas
                GROUP BY estado
            """).fetchall()

            estado_tareas = {
                fila["estado"]: fila["cantidad"]
                for fila in filas
            }

            servicio = conn.execute("""
                SELECT
                    estado,
                    fecha,
                    detalle
                FROM estado_servicio
                WHERE id = 1
            """).fetchone()

            return {
                "total":
                    sum(estado_tareas.values()),

                "pendientes":
                    estado_tareas.get(
                        "PENDIENTE",
                        0
                    ),

                "processing":
                    estado_tareas.get(
                        "PROCESSING",
                        0
                    ),

                "analizadas":
                    estado_tareas.get(
                        "ANALIZADO",
                        0
                    ),

                "revision":
                    estado_tareas.get(
                        "REVISION",
                        0
                    ),

                "verificadas":
                    estado_tareas.get(
                        "VERIFICADO",
                        0
                    ),

                "erroneas":
                    estado_tareas.get(
                        "ERRONEO",
                        0
                    ),

                "descartadas":
                    estado_tareas.get(
                        "DESCARTADO",
                        0
                    ),

                "fallos":
                    estado_tareas.get(
                        "FALLO",
                        0
                    ),

                "estado_tareas":
                    estado_tareas,

                "servicio":
                    dict(servicio)
                    if servicio
                    else None
            }

    def obtener_eventos(
        self,
        tarea_id=None,
        limite=100
    ):

        with self._conexion() as conn:

            if tarea_id is None:

                filas = conn.execute("""
                    SELECT
                        id,
                        fecha,
                        tipo,
                        tarea_id,
                        detalle
                    FROM eventos_controlador
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    limite,
                )).fetchall()

            else:

                filas = conn.execute("""
                    SELECT
                        id,
                        fecha,
                        tipo,
                        tarea_id,
                        detalle
                    FROM eventos_controlador
                    WHERE tarea_id = ?
                    ORDER BY id ASC
                    LIMIT ?
                """, (
                    tarea_id,
                    limite
                )).fetchall()

            return [
                dict(fila)
                for fila in filas
            ]

    # =========================================================
    # PROCESAMIENTO
    # =========================================================

    def procesar_siguiente_tarea(self):

        tarea = (
            self
            .obtener_siguiente_tarea_pendiente()
        )

        if tarea is None:
            return None

        print()
        print("======================================")
        print(
            f"PROCESANDO TAREA {tarea['id']}"
        )
        print("======================================")

        resultado = (
            self
            .enviar_tarea_a_viernes(
                tarea["id"]
            )
        )

        print()
        print(
            f"Tarea {tarea['id']} finalizada."
        )
        print(
            "Estado Viernes: "
            f"{resultado['estado']}"
        )

        return {
            "id": tarea["id"],
            "resultado": resultado
        }

    def procesar_cola(self):

        resultados = []

        while not self._detener.is_set():

            resultado = (
                self
                .procesar_siguiente_tarea()
            )

            if resultado is None:
                break

            resultados.append(resultado)

        return resultados

    def ejecutar_automatico(self):

        print("======================================")
        print("      CONTROLADOR VIERNES V2")
        print("======================================")
        print()
        print(
            f"BD: {self.db_path}"
        )
        print(
            "Servidor Viernes: "
            f"{self.viernes_url}"
        )
        print(
            "API Controlador: "
            f"http://{API_HOST}:{API_PORT}"
        )
        print()
        print(
            "Controlador en funcionamiento."
        )
        print(
            "Esperando trabajo..."
        )
        print()

        self._estado_servicio(
            "DISPONIBLE",
            "Controlador en funcionamiento."
        )

        while not self._detener.is_set():

            try:

                creadas = (
                    self
                    .crear_tareas_pendientes_desde_bruta()
                )

                if creadas:

                    print(
                        "Nuevas tareas creadas: "
                        f"{creadas}"
                    )

                resultados = (
                    self
                    .procesar_cola()
                )

                if resultados:

                    print()
                    print(
                        f"Procesadas: "
                        f"{len(resultados)}"
                    )
                    print()

                self._estado_servicio(
                    "DISPONIBLE",
                    "Esperando trabajo."
                )

                self._detener.wait(
                    INTERVALO_CONTROL
                )

            except Exception as error:

                print()
                print(
                    "ERROR EN CONTROLADOR:"
                )
                print(error)
                print()

                with self._conexion() as conn:

                    conn.execute("""
                        INSERT INTO errores (
                            tarea_id,
                            fecha,
                            tipo,
                            detalle
                        )
                        VALUES (
                            NULL,
                            ?,
                            'ERROR_CONTROLADOR',
                            ?
                        )
                    """, (
                        ahora(),
                        str(error)
                    ))

                    self._evento(
                        conn,
                        "ERROR_CONTROLADOR",
                        None,
                        str(error)
                    )

                self._estado_servicio(
                    "ERROR",
                    str(error)
                )

                self._detener.wait(
                    INTERVALO_CONTROL
                )

    def detener(self):

        self._detener.set()

        try:

            self._estado_servicio(
                "DETENIDO",
                "Controlador detenido por el usuario."
            )

        except Exception:
            pass

    # =========================================================
    # API
    # =========================================================

    def api_status(self):

        return {
            "ok": True,
            "servicio":
                "controlador_viernes",
            "version": "V2",
            "estado":
                self.obtener_estado()
        }


class ControladorHTTPHandler(
    BaseHTTPRequestHandler
):

    controlador = None

    def _enviar_json(
        self,
        datos,
        codigo=200
    ):

        contenido = json.dumps(
            datos,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(codigo)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(contenido))
        )

        self.end_headers()

        self.wfile.write(
            contenido
        )

    def _leer_json(self):

        longitud = int(
            self.headers.get(
                "Content-Length",
                "0"
            )
        )

        if longitud <= 0:
            return {}

        contenido = (
            self.rfile
            .read(longitud)
            .decode("utf-8")
        )

        return json.loads(
            contenido
        )

    def do_GET(self):

        try:

            ruta = urlparse(
                self.path
            ).path

            if ruta == "/":

                interfaz_path = (
                    Path(__file__).parent
                    / "interfaz.html"
                )

                if not interfaz_path.exists():

                    raise FileNotFoundError(
                        "No existe la interfaz: "
                        f"{interfaz_path}"
                    )

                contenido_interfaz = (
                    interfaz_path
                    .read_text(
                        encoding="utf-8"
                    )
                )

                datos_interfaz = (
                    contenido_interfaz
                    .encode("utf-8")
                )

                self.send_response(200)

                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8"
                )

                self.send_header(
                    "Content-Length",
                    str(len(datos_interfaz))
                )

                self.end_headers()

                self.wfile.write(
                    datos_interfaz
                )

                return

            if ruta == "/health":

                self._enviar_json({
                    "status": "ok"
                })

                return

            if ruta == "/api/status":

                self._enviar_json(
                    self.controlador.api_status()
                )

                return

            if ruta == "/api/chat":

                mensajes = datos.get(
                    "mensajes",
                    []
                )

                if not isinstance(mensajes, list):
                    raise ValueError(
                        "mensajes debe ser una lista."
                    )

                if not mensajes:
                    raise ValueError(
                        "La conversacion no puede estar vacia."
                    )

                for mensaje in mensajes:

                    if not isinstance(mensaje, dict):
                        raise ValueError(
                            "Cada mensaje debe ser un objeto."
                        )

                    if mensaje.get("role") not in {
                        "user",
                        "assistant"
                    }:
                        raise ValueError(
                            "Rol de mensaje no valido."
                        )

                    contenido = mensaje.get(
                        "content",
                        ""
                    )

                    if (
                        not isinstance(contenido, str)
                        or not contenido.strip()
                    ):
                        raise ValueError(
                            "El contenido de cada mensaje "
                            "no puede estar vacio."
                        )

                respuesta = (
                    self
                    .controlador
                    .chat_directo(
                        mensajes
                    )
                )

                self._enviar_json({
                    "ok": True,
                    "respuesta": respuesta
                })

                return
            if ruta == "/api/tareas":

                tareas = (
                    self
                    .controlador
                    .listar_tareas()
                )

                self._enviar_json({
                    "tareas": tareas
                })

                return

            if ruta == "/api/bruta":

                bruta = (
                    self
                    .controlador
                    .listar_bruta()
                )

                self._enviar_json({
                    "bruta": bruta
                })

                return

            if ruta == "/api/revision":

                revision = (
                    self
                    .controlador
                    .listar_revision()
                )

                self._enviar_json({
                    "revision": revision
                })

                return

            if ruta == "/api/conocimiento":

                conocimiento = (
                    self
                    .controlador
                    .listar_conocimiento()
                )

                self._enviar_json({
                    "conocimiento":
                        conocimiento
                })

                return

            if ruta == "/api/errores":

                errores = (
                    self
                    .controlador
                    .listar_errores()
                )

                self._enviar_json({
                    "errores": errores
                })

                return

            if ruta == "/api/eventos":

                eventos = (
                    self
                    .controlador
                    .obtener_eventos()
                )

                self._enviar_json({
                    "eventos": eventos
                })

                return

            # =================================================
            # TAREA INDIVIDUAL / CONVERSACION
            # =================================================

            if ruta.startswith(
                "/api/tareas/"
            ):

                partes = (
                    ruta
                    .strip("/")
                    .split("/")
                )

                # /api/tareas/21
                if (
                    len(partes) == 3
                    and partes[0] == "api"
                    and partes[1] == "tareas"
                ):

                    tarea_id = int(
                        partes[2]
                    )

                    tarea = (
                        self
                        .controlador
                        .mostrar_tarea(
                            tarea_id
                        )
                    )

                    if tarea is None:

                        self._enviar_json(
                            {
                                "error":
                                    "Tarea no encontrada"
                            },
                            404
                        )

                        return

                    self._enviar_json(
                        tarea
                    )

                    return

                # /api/tareas/21/conversacion
                if (
                    len(partes) == 4
                    and partes[0] == "api"
                    and partes[1] == "tareas"
                    and partes[3] == "conversacion"
                ):

                    tarea_id = int(
                        partes[2]
                    )

                    conversaciones = (
                        self
                        .controlador
                        .listar_conversacion(
                            tarea_id
                        )
                    )

                    self._enviar_json({
                        "tarea_id":
                            tarea_id,
                        "conversaciones":
                            conversaciones
                    })

                    return

            self._enviar_json(
                {
                    "error":
                        "Ruta no encontrada"
                },
                404
            )

        except ValueError as error:

            self._enviar_json(
                {
                    "error": str(error)
                },
                400
            )

        except Exception as error:

            self._enviar_json(
                {
                    "error": str(error)
                },
                500
            )

    def do_POST(self):

        try:

            ruta = urlparse(
                self.path
            ).path

            datos = self._leer_json()

            if ruta == "/api/chat":

                mensajes = datos.get(
                    "mensajes",
                    []
                )

                if not isinstance(mensajes, list):
                    raise ValueError(
                        "mensajes debe ser una lista."
                    )

                if not mensajes:
                    raise ValueError(
                        "La conversacion no puede estar vacia."
                    )

                for mensaje in mensajes:

                    if not isinstance(mensaje, dict):
                        raise ValueError(
                            "Cada mensaje debe ser un objeto."
                        )

                    if mensaje.get("role") not in {
                        "user",
                        "assistant"
                    }:
                        raise ValueError(
                            "Rol de mensaje no valido."
                        )

                    contenido = mensaje.get(
                        "content",
                        ""
                    )

                    if (
                        not isinstance(contenido, str)
                        or not contenido.strip()
                    ):
                        raise ValueError(
                            "El contenido de cada mensaje "
                            "no puede estar vacio."
                        )

                respuesta = (
                    self
                    .controlador
                    .chat_directo(
                        mensajes
                    )
                )

                self._enviar_json({
                    "ok": True,
                    "respuesta": respuesta
                })

                return
            if ruta == "/api/tareas":

                contenido = datos.get(
                    "contenido",
                    ""
                )

                tarea_id = (
                    self
                    .controlador
                    .crear_tarea_manual(
                        contenido
                    )
                )

                self._enviar_json({
                    "ok": True,
                    "tarea_id":
                        tarea_id
                }, 201)

                return

            if ruta == "/api/bruta":

                contenido = datos.get(
                    "contenido",
                    ""
                )

                origen = datos.get(
                    "origen",
                    "API"
                )

                if (
                    not contenido
                    or not contenido.strip()
                ):

                    raise ValueError(
                        "El contenido BRUTA "
                        "no puede estar vacío."
                    )

                with (
                    self.controlador
                    ._conexion()
                ) as conn:

                    cursor = conn.execute("""
                        INSERT INTO bruta (
                            fecha,
                            contenido,
                            origen
                        )
                        VALUES (?, ?, ?)
                    """, (
                        ahora(),
                        contenido.strip(),
                        origen
                    ))

                    bruta_id = (
                        cursor.lastrowid
                    )

                self._enviar_json({
                    "ok": True,
                    "bruta_id":
                        bruta_id
                }, 201)

                return

            if (
                ruta.startswith(
                    "/api/tareas/"
                )
                and
                ruta.endswith(
                    "/verificar"
                )
            ):

                partes = (
                    ruta
                    .strip("/")
                    .split("/")
                )

                if (
                    len(partes) != 4
                    or partes[0] != "api"
                    or partes[1] != "tareas"
                    or partes[3] != "verificar"
                ):
                    raise ValueError(
                        "Ruta de verificación no válida."
                    )

                tarea_id = int(
                    partes[2]
                )

                estado = datos.get(
                    "estado"
                )

                comentario = datos.get(
                    "comentario",
                    ""
                )

                contenido_verificado = datos.get(
                    "contenido_verificado",
                    ""
                )

                resultado = (
                    self
                    .controlador
                    .verificar_tarea(
                        tarea_id,
                        estado,
                        comentario,
                        contenido_verificado
                    )
                )

                self._enviar_json(
                    resultado
                )

                return

            if (
                ruta
                == "/api/controlador/detener"
            ):

                (
                    self
                    .controlador
                    .detener()
                )

                self._enviar_json({
                    "ok": True,
                    "estado":
                        "DETENIDO"
                })

                return

            self._enviar_json(
                {
                    "error":
                        "Ruta no encontrada"
                },
                404
            )

        except ValueError as error:

            self._enviar_json(
                {
                    "error": str(error)
                },
                400
            )

        except Exception as error:

            self._enviar_json(
                {
                    "error": str(error)
                },
                500
            )

    def log_message(
        self,
        formato,
        *args
    ):

        print(
            "[API]",
            formato % args
        )


def iniciar_api(
    controlador
):

    ControladorHTTPHandler.controlador = (
        controlador
    )

    servidor = ThreadingHTTPServer(
        (
            API_HOST,
            API_PORT
        ),
        ControladorHTTPHandler
    )

    hilo = threading.Thread(
        target=servidor.serve_forever,
        daemon=True
    )

    hilo.start()

    print(
        "API del controlador "
        f"escuchando en "
        f"http://{API_HOST}:{API_PORT}"
    )

    return servidor


def main():

    controlador = Controlador()

    servidor_api = iniciar_api(
        controlador
    )

    try:

        controlador.ejecutar_automatico()

    except KeyboardInterrupt:

        print()
        print(
            "Controlador detenido "
            "por el usuario."
        )

    finally:

        controlador.detener()

        servidor_api.shutdown()

        servidor_api.server_close()


if __name__ == "__main__":
    main()
