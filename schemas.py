from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class UIComponent(BaseModel):
    type: str = Field(description="O tipo do componente React. Ex: 'CustomsPriorityCard' ou 'LogisticsTimeline'.")
    props: Dict[str, Any] = Field(description="As propriedades (props) que o React vai usar para renderizar.")

class TAISAResponse(BaseModel):
    message: str = Field(description="A mensagem em linguagem natural amigável da TAISA respondendo à dúvida do usuário.")
    ui_component: Optional[UIComponent] = Field(description="Definição do componente visual, se aplicável ao cenário.")