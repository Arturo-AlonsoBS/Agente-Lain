"""
Cliente para la API de Gemini (Interactions API).
Usa previous_interaction_id para que Gemini mantenga el contexto
de la conversación del lado del servidor (no hace falta reenviar
todo el historial en cada mensaje).
"""
from google import genai
from config import settings

SYSTEM_PROMPT = """Sos LAIN, un agente que responde preguntas basándote
únicamente en el contenido de los documentos (PDF o CSV) que el usuario cargó.

Reglas:
1. Respondé siempre en español, de forma clara y directa.
2. Si la respuesta está en el contexto, mencioná de qué documento sale, si es posible en qué párrafo y/o página.
3. Si el contexto no tiene la respuesta, decilo explícitamente: "No encontré
   esa información en el documento cargado."
4. No inventes datos que no estén en el contexto.
"""


class GeminiClient:
    def __init__(self):
        print(f"Inicializando Gemini: {settings.llm_model}")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.llm_model
        print("Gemini listo")
    

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
        try:
            interaction = self.client.interactions.create(
                model=self.model,
                input=prompt,
                system_instruction=SYSTEM_PROMPT,
                previous_interaction_id=previous_interaction_id,
                generation_config={"temperature": 0.5, "max_output_tokens": 1024},
            )
        except Exception:
            if previous_interaction_id:
                interaction = self.client.interactions.create(
                    model=self.model,
                    input=prompt,
                    system_instruction=SYSTEM_PROMPT,
                    previous_interaction_id=None,
                    generation_config={"temperature": 0.5, "max_output_tokens": 1024},
                )
            else:
                raise

        return {
            "answer": interaction.output_text,
            "interaction_id": interaction.id,
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
