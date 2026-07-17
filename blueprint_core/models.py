from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
import re

# ==========================================
# 1. Base / Seed Component Database Schemas
# ==========================================

class PinDefinition(BaseModel):
    pin_id: str = Field(..., description="Unique pin identifier, e.g., '1', 'GND', 'D13'")
    name: str = Field(..., description="Pin functional name, e.g., 'VCC', 'TX', 'GPIO4'")
    pin_type: str = Field(..., description="Type of pin: Power, Ground, Digital, Analog, I2C, SPI, UART, PWM, Passive")
    voltage: Optional[float] = Field(None, description="Operating voltage of the pin in Volts, e.g., 3.3 or 5.0")
    description: Optional[str] = Field(None, description="Detailed description of the pin function")

class ComponentTemplate(BaseModel):
    part_number: str = Field(..., description="Manufacturer or generic part number, e.g., 'ESP32-WROOM-32D', 'DHT11'")
    name: str = Field(..., description="Friendly name of the component, e.g., 'ESP32 Development Board'")
    category: str = Field(..., description="Category: Microcontroller, Sensor, Actuator, Display, Power, Passives, Communication")
    description: str = Field(..., description="Short explanation of what this part does")
    price: float = Field(0.0, description="Estimated unit price in USD")
    sourcing_url: Optional[str] = Field(None, description="Sourcing or datasheet link")
    pins: List[PinDefinition] = Field(default_factory=list, description="List of physical pins on the component")
    use_cases: List[str] = Field(default_factory=list, description="Common use cases or keywords")

# ==========================================
# 2. Project-Level Hardware IR (Shared State)
# ==========================================

class ProjectOverview(BaseModel):
    title: str = Field(..., description="Title of the hardware project")
    description: str = Field(..., description="Summary of the project")
    difficulty: str = Field(..., description="Difficulty level: Beginner, Intermediate, Advanced")
    estimated_cost: float = Field(0.0, description="Total estimated BOM cost in USD")
    category: str = Field(..., description="Primary project domain: IoT, Wearable, Automation, Robotics, Smart Home")

class FunctionalRequirements(BaseModel):
    requirements: List[str] = Field(default_factory=list, description="List of primary functional requirements")
    power_needs: str = Field(..., description="Power supply requirements, e.g., '5V USB', '3.7V LiPo Battery'")
    operating_voltage: float = Field(3.3, description="Main operating system voltage, typically 3.3 or 5.0")
    physical_constraints: List[str] = Field(default_factory=list, description="Size, weight, or environmental constraints")
    safety_notes: List[str] = Field(default_factory=list, description="Safety and handling advisories")
    missing_info: List[str] = Field(default_factory=list, description="Clarifying questions or unknown requirements")

class ComponentInstance(BaseModel):
    ref_des: str = Field(..., description="Reference designator, e.g., 'U1', 'R1', 'SEN1'")
    part_number: str = Field(..., description="Matching part number from the template database")
    name: str = Field(..., description="Display name of this instance")
    category: str = Field(..., description="Category of the component")
    quantity: int = Field(1, description="Quantity required")
    unit_price: float = Field(0.0, description="Estimated unit price in USD")
    sourcing_url: Optional[str] = Field(None, description="Sourcing URL")
    rationale: str = Field(..., description="Why this component was selected for this project")
    pins: List[PinDefinition] = Field(default_factory=list, description="Full pinout of the instantiated component")

class PinReference(BaseModel):
    ref_des: str = Field(..., description="Component reference designator, e.g., 'U1'")
    pin_id: str = Field(..., description="Pin ID on the target component, e.g., 'GND' or '12'")

class ConnectionNet(BaseModel):
    net_id: str = Field(..., description="Unique ID for the electrical net, e.g., 'NET_VCC', 'NET_I2C_SDA'")
    name: str = Field(..., description="Friendly net name, e.g., '3.3V Power Rail', 'I2C Data'")
    net_type: str = Field(..., description="Net type: Power, Ground, Analog, Digital, I2C, SPI, UART, PWM")
    voltage: Optional[float] = Field(None, description="Expected voltage of this net, e.g., 3.3")
    pins: List[PinReference] = Field(default_factory=list, description="All component pins tied to this net")

class AssemblyStep(BaseModel):
    step_num: int = Field(..., description="Index order of this assembly instruction")
    title: str = Field(..., description="Short title of the step")
    description: str = Field(..., description="Step-by-step assembly description")
    danger_flag: bool = Field(False, description="True if step carries electric, thermal, or physical risk")
    danger_message: Optional[str] = Field(None, description="Warning warning note for this step")
    affected_components: List[str] = Field(default_factory=list, description="Reference designators of components handled in this step")

class MechanicalSource(BaseModel):
    name: str = Field(..., description="Display name of the CAD, enclosure, or fabrication source")
    source_type: str = Field(..., description="Source class: Open STL, Paid STL, Vendor CAD, Reference CAD, or Fabrication Estimate")
    url: str = Field(..., description="Resolvable source URL for the CAD model, enclosure datasheet, or fabrication reference")
    file_formats: List[str] = Field(default_factory=list, description="Known CAD/download formats such as STL, STEP, DXF, or Fusion 360")
    license: Optional[str] = Field(None, description="Source license or commercial availability note")
    estimated_unit_price_usd: float = Field(0.0, description="Estimated CAD download, fabrication, or enclosure unit cost in USD")
    notes: Optional[str] = Field(None, description="How this source should be adapted for the generated design")

class MechanicalVector3(BaseModel):
    x_mm: float = Field(..., description="X-axis measurement in millimeters, where X is project width")
    y_mm: float = Field(..., description="Y-axis measurement in millimeters, where Y is project depth")
    z_mm: float = Field(..., description="Z-axis measurement in millimeters, where Z is project height")

class MechanicalRotation3(BaseModel):
    x_deg: float = Field(0.0, description="Rotation around the X axis in degrees")
    y_deg: float = Field(0.0, description="Rotation around the Y axis in degrees")
    z_deg: float = Field(0.0, description="Rotation around the Z axis in degrees")

class MechanicalPlacement(BaseModel):
    ref_des: str = Field(..., description="Reference designator of the component this placement represents")
    label: Optional[str] = Field(None, description="Display label for the placed component")
    category: Optional[str] = Field(None, description="Component class or placement layer such as Microcontroller, Display, 3D Print, or Mechanical")
    layer: str = Field("electrical", description="Visibility layer: electrical, mechanism, print, enclosure, structural, or misc")
    position: MechanicalVector3 = Field(..., description="Component center position in millimeters relative to the enclosure center")
    size: MechanicalVector3 = Field(..., description="Approximate component envelope size in millimeters")
    orientation_deg: MechanicalRotation3 = Field(default_factory=MechanicalRotation3, description="Euler orientation in degrees around X, Y, and Z")
    mounting_face: Optional[str] = Field(None, description="Face or surface used for mounting, such as front, back, floor, lid, left, or right")
    notes: Optional[str] = Field(None, description="Clearance, fastener, cable routing, or assembly notes for this placement")

class MechanicalSpatialRelationship(BaseModel):
    source_ref_des: str = Field(..., description="Reference designator of the source component")
    target_ref_des: str = Field(..., description="Reference designator of the target component")
    relation: str = Field(..., description="Physical relationship such as centered-above, adjacent-to, mounted-on, aligned-with, or clearance-from")
    axis: Optional[str] = Field(None, description="Dominant axis for the relationship: X, Y, or Z")
    offset_mm: Optional[float] = Field(None, description="Signed offset between components along the dominant axis")
    notes: Optional[str] = Field(None, description="Additional placement or clearance rationale")

class MechanicalNotes(BaseModel):
    enclosure_type: str = Field(..., description="Type of housing: 3D Printed, Off-the-shelf, Custom Acrylic, Waterproof, Acrylic laser cut")
    mounting_guidance: str = Field(..., description="Mounting and standoffs instructions")
    fabrication_details: List[str] = Field(default_factory=list, description="Enclosure dimensions, material recommendations, or printing instructions")
    fabrication_cost_estimate_usd: float = Field(0.0, description="Estimated mechanical fabrication cost in USD, excluding electrical BOM")
    cad_sources: List[MechanicalSource] = Field(default_factory=list, description="CAD, enclosure, and fabrication source records")
    manufacturability_rating: str = Field(..., description="Ease of manufacturing: Easy, Moderate, Challenging")
    render_dimensions: Optional[MechanicalVector3] = Field(None, description="Overall live-render envelope dimensions in millimeters")
    component_placements: List[MechanicalPlacement] = Field(default_factory=list, description="Per-component 3D placements for live Three.js rendering")
    spatial_relationships: List[MechanicalSpatialRelationship] = Field(default_factory=list, description="Physical offsets and alignment relationships between placed components")

class PinMappingEntry(BaseModel):
    mcu_pin: str = Field(..., description="MCU pin identifier, e.g., 'GPIO23'")
    connected_to: str = Field(..., description="Name of the sensor pin/function connected, e.g., 'DHT22 Data'")
    net_name: str = Field(..., description="Electrical net name, e.g., 'DHT_SDA_NET'")

class ValidationIssue(BaseModel):
    severity: str = Field(..., description="Severity level: CRITICAL, WARNING, or INFO")
    category: str = Field(..., description="Short circuit, Voltage Mismatch, Unpowered IC, Pin Conflict, Overcurrent, Safety Block")
    description: str = Field(..., description="Detailed description of the validation issue")
    troubleshooting: str = Field(..., description="Suggested remediation action for self-healing or user override")

class ValidationSummary(BaseModel):
    critical: List[ValidationIssue] = Field(default_factory=list, description="Critical blocking issues or errors")
    warning: List[ValidationIssue] = Field(default_factory=list, description="Warning level issues")
    info: List[ValidationIssue] = Field(default_factory=list, description="Informational recommendations")

class BusConnection(BaseModel):
    bus_id: str = Field(..., description="Unique ID for the digital communication bus, e.g., 'BUS_I2C_1'")
    bus_type: str = Field(..., description="Bus type: I2C, SPI, UART, CAN")
    clock_frequency_hz: Optional[float] = Field(None, description="Operating bus speed if applicable")
    nets: List[str] = Field(default_factory=list, description="Electrical net IDs associated with this bus")

class PowerRail(BaseModel):
    rail_id: str = Field(..., description="Unique ID for power rail, e.g., 'RAIL_3V3'")
    voltage: float = Field(..., description="Nominal operating voltage in Volts")
    max_current_capacity_ma: float = Field(..., description="Maximum continuous current capacity in mA")
    source_component: str = Field(..., description="Reference designator of the power source component")

class HardwareIR(BaseModel):
    """The master typed document capturing the entire generated hardware design."""
    hardware_ir_version: str = Field("0.1", description="Structured schema version")
    overview: Optional[ProjectOverview] = Field(None, description="Project overview metadata")
    requirements: Optional[FunctionalRequirements] = Field(None, description="Extracted constraints & requirements")
    components: List[ComponentInstance] = Field(default_factory=list, description="Instantiated Bill of Materials")
    nets: List[ConnectionNet] = Field(default_factory=list, description="Electrical netlist connections")
    buses: List[BusConnection] = Field(default_factory=list, description="Digital communication buses")
    pin_mappings: List[PinMappingEntry] = Field(default_factory=list, description="MCU functional pin map")
    assembly: List[AssemblyStep] = Field(default_factory=list, description="Step-by-step physical build instruction package")
    mechanical: Optional[MechanicalNotes] = Field(None, description="Enclosure and fabrications specifications")
    
    # Extra requested fields
    constraints: List[str] = Field(default_factory=list, description="Project architectural and electrical constraints")
    power_rails: List[PowerRail] = Field(default_factory=list, description="Active power delivery rails")
    estimated_current_draw_ma: float = Field(0.0, description="Total calculated peak current consumption in mA")
    fabrication_notes: List[str] = Field(default_factory=list, description="Printed circuit/manufacturability and casing guidelines")
    assembly_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional builder metadata and configurations")
    project_version_history: List[Dict[str, Any]] = Field(default_factory=list, description="Revision and modification history of this project package")
    
    validation: ValidationSummary = Field(default_factory=ValidationSummary, description="Categorized safety and electrical checks")
    is_valid: bool = Field(True, description="True if project passes critical validation checks")

# ==========================================
# 3. API Requests & Response Models
# ==========================================

class GenerateProjectRequest(BaseModel):
    prompt: str = Field(..., description="User's natural language project description")
    workflow: str = Field(
        "default",
        description="Generation workflow id: default or web_research"
    )
    image_data: Optional[str] = Field(
        None,
        description="Optional data URL or base64-encoded reference image for multimodal project extraction"
    )
    generate_image: bool = Field(
        False,
        description="When true, generate a product concept image with the configured image provider"
    )
    provider: Optional[str] = Field(
        None,
        description="Optional runtime LLM provider override, for example openai, baseten, gmi, huggingface, nvidia, openai-compatible, gemini, runpod, runpod-serverless, or simulation"
    )
    model: Optional[str] = Field(
        None,
        description="Optional runtime model override. Must be allowed for the selected provider."
    )
    chat_id: Optional[str] = Field(
        None,
        description="Optional chat/thread id that owns the generated project."
    )
    source_project_id: Optional[str] = Field(
        None,
        description="Optional project id that this generation was requested from."
    )
    client_job_id: Optional[str] = Field(
        None,
        description="Optional frontend-generated job id for progress polling."
    )
    external_source_provider: Optional[str] = Field(
        None,
        description="Optional web research provider override. Supported values: firecrawl or tavily."
    )

    @field_validator("provider", "model", "chat_id", "source_project_id", "client_job_id", "external_source_provider", mode="before")
    @classmethod
    def strip_optional_generation_selector(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("client_job_id")
    @classmethod
    def validate_client_job_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value):
            raise ValueError("client_job_id may only contain letters, numbers, dot, dash, underscore, or colon.")
        return value

    @field_validator("external_source_provider")
    @classmethod
    def validate_external_source_provider(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower().replace("_", "-")
        if normalized == "auto":
            return "firecrawl"
        if normalized in {"tavily", "firecrawl"}:
            return normalized
        raise ValueError("external_source_provider must be firecrawl or tavily.")


class ClarifyingQuestion(BaseModel):
    id: str = Field(..., min_length=1, description="Stable question id.")
    label: str = Field(..., min_length=1, description="Short UI label for the question.")
    question: str = Field(..., min_length=1, description="Question to ask the user.")
    placeholder: str = Field("", description="Optional example answer or placeholder.")
    suggestions: List[str] = Field(default_factory=list, description="Short suggested answer chips.")


class ClarifyingQuestionsRequest(BaseModel):
    prompt: str = Field("", description="User's natural language project description.")
    workflow: str = Field("default", description="Generation workflow id.")
    has_image: bool = Field(False, description="Whether the user supplied a reference image.")
    max_questions: int = Field(3, ge=0, le=5, description="Maximum number of clarifying questions to return.")
    force: bool = Field(True, description="When true, ask useful context questions unless the user explicitly skips them.")

    @field_validator("prompt", "workflow", mode="before")
    @classmethod
    def strip_clarifier_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class ClarifyingQuestionsResponse(BaseModel):
    agent: str = Field("Context Clarifier Agent", description="Agent that produced the questions.")
    should_ask: bool = Field(False, description="Whether the UI should pause and ask these questions.")
    reason: str = Field("", description="Short reason for the clarification decision.")
    questions: List[ClarifyingQuestion] = Field(default_factory=list)
    workflow: str = Field("default")


class IterateProjectRequest(BaseModel):
    instruction: str = Field(..., min_length=1, description="Natural language change request to apply to an existing project")
    namespace: Optional[str] = Field(
        None,
        description="Optional dotted project object namespace to target, for example product.mech or project.docs.",
    )
    provider: Optional[str] = Field(
        None,
        description="Optional runtime LLM provider override for the iteration.",
    )
    model: Optional[str] = Field(
        None,
        description="Optional runtime model override for the iteration.",
    )
    save: bool = Field(True, description="When true, persist the revised HardwareIR over the existing project record.")

    @field_validator("instruction", mode="before")
    @classmethod
    def strip_iteration_instruction(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class VideoSelfCorrectRequest(BaseModel):
    video_url: str = Field(..., min_length=1, description="HTTP(S) URL for the generated video to review.")
    video_key: Optional[str] = Field(
        None,
        description="Optional saved video object key. Used to verify the review target belongs to this project.",
    )
    namespace: Optional[str] = Field(
        None,
        description="Optional project namespace to target for the corrective iteration.",
    )
    provider: Optional[str] = Field(
        None,
        description="Optional runtime LLM provider override for applying the iteration.",
    )
    model: Optional[str] = Field(
        None,
        description="Optional runtime LLM model override for applying the iteration.",
    )
    review_model: Optional[str] = Field(
        None,
        description="Optional Fireworks review model override. Defaults to kimi-k2p6 frame review unless native video deployment routing is configured.",
    )
    save: bool = Field(True, description="When true, persist the revised HardwareIR over the existing project record.")

    @field_validator("video_url", mode="before")
    @classmethod
    def strip_video_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("video_key", "namespace", "provider", "model", "review_model", mode="before")
    @classmethod
    def strip_optional_video_review_selector(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("video_url")
    @classmethod
    def validate_video_url(cls, value: str) -> str:
        if not re.match(r"^https?://", value):
            raise ValueError("video_url must be an http(s) URL.")
        return value

    @field_validator("namespace", "provider", "model", mode="before")
    @classmethod
    def strip_optional_iteration_selector(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class AlphaSignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Person's name")
    email: str = Field(..., min_length=3, max_length=254, description="Contact email")
    organization: Optional[str] = Field(None, max_length=160, description="Organization or team")
    additional_info: Optional[str] = Field(None, max_length=1200, description="Optional launch or use-case context")

    @field_validator("name", "email", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("organization", "additional_info", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("name")
    @classmethod
    def require_name(cls, value: Optional[str]) -> str:
        if not value:
            raise ValueError("Name is required.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> str:
        if not value:
            raise ValueError("Email is required.")
        normalized = value.lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class AlphaSignupResponse(BaseModel):
    ok: bool
    message: str


class ValidationReport(BaseModel):
    is_valid: bool
    issues: List[ValidationIssue]
