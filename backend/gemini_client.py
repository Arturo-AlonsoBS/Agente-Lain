"""
Cliente para la API de Gemini (Interactions API).
Usa previous_interaction_id para que Gemini mantenga el contexto
de la conversación del lado del servidor (no hace falta reenviar
todo el historial en cada mensaje).
"""
import uuid
from google import genai
from config import settings

SYSTEM_PROMPT = """Sos LAIN, un agente que responde preguntas basándote
principalmente en el contenido de los documentos (PDF o CSV) que el usuario cargó
y en el contexto de la conversación previa cuando exista.

Reglas:
1. Respondé siempre en español, de forma clara y directa.
2. Si el usuario ya te dio un dato personal o un contexto importante antes,
   recordalo y úsalo correctamente en la conversación.
3. Si la respuesta está en el contexto, mencioná de qué documento sale, si es
   posible en qué párrafo y/o página.
4. Si el contexto no tiene la respuesta, decilo explícitamente: "No encontré
   esa información en el documento cargado."
5. No inventes datos que no estén en el contexto.
6. No incluyas un bloque de "SOURCES" o referencias de fuentes al final del texto.
7. Sé completo pero directo: no repitas la pregunta, no agregues relleno
   innecesario antes de la respuesta.
8. Nada de emojis o insultos o comentarios de humor. Sé profesional y neutral.
"""


class GeminiClient:
    def __init__(self):
        print(f"Inicializando Gemini: {settings.llm_model}")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.llm_model
        self._sessions: dict = {}
        print("Gemini listo")

    def ask(self, question: str, context: str, previous_interaction_id: str = None):
        prompt = f"""Contexto recuperado de los documentos:
{context if context else "(no se encontró contexto relevante)"}

---

Pregunta del usuario: {question}
"""
        gen_config = {
            "temperature": 0.4,
            "max_output_tokens": settings.llm_max_output_tokens,
            "system_instruction": SYSTEM_PROMPT,
        }

        session_id = previous_interaction_id
        chat = self._sessions.get(session_id) if session_id else None

        if chat is None:
            chat = self.client.chats.create(model=self.model, config=gen_config)
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = chat
            print(f"[ask] sesión NUEVA creada: {session_id}")
        else:
            print(f"[ask] reusando sesión {session_id}, historial previo: {len(chat.get_history())} mensajes")

        response = chat.send_message(prompt)
        answer = getattr(response, "text", None)

        print(f"[ask] historial DESPUÉS de responder: {len(chat.get_history())} mensajes")

        return {
            "answer": answer,
            "interaction_id": session_id,
        }


_client: GeminiClient = None


def init_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


def get_client() -> GeminiClient:
    if _client is None:
        raise RuntimeError("GeminiClient no inicializado")
    return _client

'''
    def ask(self, question: str, context: str, previous_interaction_id: str = None):
        """
        Envía la pregunta + contexto (RAG) a Gemini.
        Si previous_interaction_id viene seteado, Gemini recupera el
        historial de esa conversación.
        """
        prompt = f"""Contexto recuperado de los documentos:
{context if context else "(no se encontró contexto relevante)"}

---

Pregunta del usuario: {question}
"""
        gen_config = {
            "temperature": 0.5,
            "max_output_tokens": settings.llm_max_output_tokens,
        }

        try:
            interaction = self.client.interactions.create(
                model=self.model,
                input=prompt,
                system_instruction=SYSTEM_PROMPT,
                previous_interaction_id=previous_interaction_id,
                generation_config=gen_config,
            )
        except Exception:
            if previous_interaction_id:
                # El previous_interaction_id puede haber vencido/ser inválido.
                # Reintentamos como conversación nueva en vez de romper.
                interaction = self.client.interactions.create(
                    model=self.model,
                    input=prompt,
                    system_instruction=SYSTEM_PROMPT,
                    previous_interaction_id=None,
                    generation_config=gen_config,
                )
            else:
                raise

        answer = interaction.output_text

        # Aviso interno en logs si la respuesta se cortó por límite de tokens,
        # para que sea fácil de diagnosticar si vuelve a pasar.
        finish_reason = getattr(interaction, "status", None)
        usage = getattr(interaction, "usage", None)
        if usage and getattr(usage, "total_output_tokens", 0) >= settings.llm_max_output_tokens - 5:
            print(
                f" La respuesta probablemente se cortó por max_output_tokens "
                f"({settings.llm_max_output_tokens}). Considerá subirlo más en config.py."
            )

        return {
            "answer": answer,
            "interaction_id": interaction.id,
        }
'''

_client: GeminiClient = None


def init_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


def get_client() -> GeminiClient:
    if _client is None:
        raise RuntimeError("GeminiClient no inicializado")
    return _client