class CharacterManager:
    """Manages character card settings."""

    def __init__(self):
        self.name = ""
        self.character_prompt = ""
        self.video_system_prompt = ""
        self.video_prompt = ""
        self.canvas_system_prompt = ""
        self.canvas_prompt = ""
        self.starting_messages = []
        self.voice = ""
        self.base_model = ""
        self.is_video_transcription_enabled = False
        self.is_video_transcription_continuous = False
        self.video_transcription_model = ""
        self.video_transcription_interval = 0
        self.is_canvas_enabled = False
        self.canvas_model = None
        self.canvas_interval = 0
        self.character_loaded = False
        self.id = ""

    def update_from_card(self, character_card):
        self.id = character_card.get("id") if character_card.get("id", "") != "" else self.id
        self.name = character_card.get("name") if character_card.get("name", "") != "" else self.name
        self.character_prompt = character_card.get("character_prompt") if character_card.get("character_prompt", "") != "" else self.character_prompt
        self.video_system_prompt = character_card.get("video_system_prompt") if character_card.get("video_system_prompt", "") != "" else self.video_system_prompt
        self.video_prompt = character_card.get("video_prompt") if character_card.get("video_prompt", "") != "" else self.video_prompt
        self.canvas_system_prompt = character_card.get("canvas_system_prompt") if character_card.get("canvas_system_prompt", "") != "" else self.canvas_system_prompt
        self.canvas_prompt = character_card.get("canvas_prompt") if character_card.get("canvas_prompt", "") != "" else self.canvas_prompt
        self.starting_messages = character_card.get("starting_messages") if character_card.get("starting_messages", []) != [] else self.starting_messages
        self.voice = character_card.get("voice") if character_card.get("voice", "") != "" else self.voice
        self.base_model = character_card.get("base_model") if character_card.get("base_model", "") != "" else self.base_model
        self.is_video_transcription_enabled = bool(character_card.get("is_video_transcription_enabled")) if character_card.get("is_video_transcription_enabled", "") != "" else self.is_video_transcription_enabled
        self.is_video_transcription_continuous = bool(character_card.get("is_video_transcription_continuous")) if character_card.get("is_video_transcription_continuous", "") != "" else self.is_video_transcription_continuous
        self.video_transcription_model = character_card.get("video_transcription_model") if character_card.get("video_transcription_model", "") != "" else self.video_transcription_model
        self.video_transcription_interval = int(character_card.get("video_transcription_interval")) if character_card.get("video_transcription_interval", "") != "" else self.video_transcription_interval
        self.is_canvas_enabled = bool(character_card.get("is_canvas_enabled")) if character_card.get("is_canvas_enabled", "") != "" else self.is_canvas_enabled
        self.canvas_model = character_card.get("canvas_model") if character_card.get("canvas_model", "") != "" else self.canvas_model
        self.canvas_interval = int(character_card.get("canvas_interval")) if character_card.get("canvas_interval", "") != "" else self.canvas_interval
        self.character_loaded = True