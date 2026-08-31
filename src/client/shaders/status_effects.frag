#version 330 core

in vec2 fragmentTexCoord;

uniform sampler2D imageTexture;
uniform sampler2D guiTexture;
uniform float guiStrength;
uniform float readbackTopDown;
uniform vec2 resolution;
uniform float timeSeconds;
uniform float nauseaStrength;
uniform float blindnessStrength;
uniform float nightVisionStrength;

out vec4 fragmentColor;

vec2 nauseaUv(vec2 uv) {
    if (nauseaStrength <= 0.0001) {
        return uv;
    }

    vec2 centered = uv - vec2(0.5);
    float aspect = resolution.x / max(resolution.y, 1.0);
    vec2 metric = vec2(centered.x * aspect, centered.y);
    float radius = length(metric);
    float angle = sin(timeSeconds * 1.85) * 0.055 * nauseaStrength;
    float radialWave = sin(radius * 24.0 - timeSeconds * 4.2);
    angle += radialWave * 0.018 * nauseaStrength * (1.0 - min(radius, 1.0));

    float sine = sin(angle);
    float cosine = cos(angle);
    mat2 rotation = mat2(cosine, -sine, sine, cosine);
    centered = rotation * centered;
    centered *= 1.0 + radialWave * 0.018 * nauseaStrength;
    centered.x += sin(uv.y * 18.0 + timeSeconds * 2.8) * 0.006 * nauseaStrength;
    centered.y += cos(uv.x * 16.0 - timeSeconds * 2.4) * 0.005 * nauseaStrength;
    return clamp(centered + vec2(0.5), vec2(0.001), vec2(0.999));
}

vec3 sampleNausea(vec2 uv) {
    vec2 distortedUv = nauseaUv(uv);
    if (nauseaStrength <= 0.0001) {
        return texture(imageTexture, distortedUv).rgb;
    }

    vec2 direction = distortedUv - vec2(0.5);
    float lengthSquared = max(dot(direction, direction), 0.0001);
    vec2 chromaOffset = direction * inversesqrt(lengthSquared)
        * 0.0035 * nauseaStrength;
    float red = texture(imageTexture, clamp(distortedUv + chromaOffset, 0.001, 0.999)).r;
    float green = texture(imageTexture, distortedUv).g;
    float blue = texture(imageTexture, clamp(distortedUv - chromaOffset, 0.001, 0.999)).b;
    return vec3(red, green, blue);
}

vec3 applyNightVision(vec3 color) {
    if (nightVisionStrength <= 0.0001) {
        return color;
    }

    float brightest = max(max(color.r, color.g), color.b);
    vec3 normalized = color / max(brightest, 0.075);
    vec3 lifted = mix(color, normalized, 0.72);
    lifted *= vec3(0.96, 1.03, 0.94);
    return mix(color, clamp(lifted, 0.0, 1.0), nightVisionStrength);
}

vec3 applyBlindness(vec3 color, vec2 uv) {
    if (blindnessStrength <= 0.0001) {
        return color;
    }

    vec2 centered = uv - vec2(0.5);
    float aspect = resolution.x / max(resolution.y, 1.0);
    float distanceFromCenter = length(vec2(centered.x * aspect, centered.y));
    float innerRadius = mix(0.38, 0.085, blindnessStrength);
    float outerRadius = innerRadius + mix(0.34, 0.16, blindnessStrength);
    float vignette = smoothstep(innerRadius, outerRadius, distanceFromCenter);
    float dim = 0.38 * blindnessStrength;
    color *= 1.0 - dim;
    return mix(color, vec3(0.0), vignette * min(1.0, blindnessStrength * 1.12));
}

void main() {
    // Direct Surface uploads are top-to-bottom while OpenGL texture coordinates
    // are bottom-to-top.  A window framebuffer is displayed bottom-to-top, while
    // glReadPixels returns its bottom row first.  In offscreen mode, sampling Y
    // directly makes that readback buffer top-to-bottom already and avoids a
    // second full-frame CPU flip/copy.
    float textureY = mix(
        1.0 - fragmentTexCoord.y,
        fragmentTexCoord.y,
        readbackTopDown
    );
    vec2 uv = vec2(fragmentTexCoord.x, textureY);
    vec3 worldColor = sampleNausea(uv);
    worldColor = applyNightVision(worldColor);
    worldColor = applyBlindness(worldColor, uv);

    vec4 guiColor = vec4(0.0);
    if (guiStrength > 0.5) {
        guiColor = texture(guiTexture, uv);
    }
    vec3 composited = mix(worldColor, guiColor.rgb, guiColor.a);
    fragmentColor = vec4(composited, 1.0);
}
