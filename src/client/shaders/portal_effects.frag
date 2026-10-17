#version 330 core

in vec2 fragmentTexCoord;
uniform sampler2D imageTexture;
uniform sampler2D guiTexture;
uniform float guiStrength;
uniform float readbackTopDown;
uniform vec2 resolution;
uniform float timeSeconds;
uniform float portalStrength;
out vec4 fragmentColor;

const float DISTORTION_SPEED_DEG_PER_SEC = 400.0;

void main() {
    float y = mix(1.0 - fragmentTexCoord.y, fragmentTexCoord.y, readbackTopDown);
    vec2 uv = vec2(fragmentTexCoord.x, y);
    vec2 c = uv - vec2(0.5);
    float aspect = resolution.x / max(resolution.y, 1.0);
    // EntityRenderer.setupCameraTransform: rotate, stretch, rotate back.
    // Use its inverse for sampling the already composited world and overlay.
    float scale = 5.0 / (portalStrength * portalStrength + 5.0) - portalStrength * 0.04;
    scale *= scale;
    float angle = radians(timeSeconds * DISTORTION_SPEED_DEG_PER_SEC);
    float s = sin(angle), co = cos(angle);
    c.x *= aspect;
    c = mat2(co, -s, s, co) * c;
    c.x *= scale;
    c = mat2(co, s, -s, co) * c;
    c.x /= aspect;
    vec2 warped = clamp(c + vec2(0.5), vec2(0.001), vec2(0.999));
    vec3 color = texture(imageTexture, warped).rgb;
    vec4 gui = guiStrength > 0.5 ? texture(guiTexture, uv) : vec4(0.0);
    fragmentColor = vec4(mix(color, gui.rgb, gui.a), 1.0);
}