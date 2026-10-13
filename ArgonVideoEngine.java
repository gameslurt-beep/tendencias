import java.awt.*;
import java.awt.geom.*;
import java.awt.image.BufferedImage;
import java.awt.image.DataBufferByte;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import javax.sound.sampled.*;

public class ArgonVideoEngine {

    // Configurações do Vídeo (Formato Shorts / Vertical 60 FPS)
    private static final int WIDTH = 1080;
    private static final int HEIGHT = 1920;
    private static final int FPS = 60;
    private static final int DURATION_SEC = 6;
    private static final int TOTAL_FRAMES = FPS * DURATION_SEC;

    static class Particle {
        float x, y, z, vx, vy, size;
        Color color;

        Particle(Random rnd) {
            reset(rnd, true);
        }

        void reset(Random rnd, boolean randomY) {
            x = (rnd.nextFloat() - 0.5f) * WIDTH * 1.5f;
            y = randomY ? (rnd.nextFloat() - 0.5f) * HEIGHT * 1.5f : HEIGHT * 0.8f;
            z = 0.2f + rnd.nextFloat() * 1.8f;
            vx = (rnd.nextFloat() - 0.5f) * 1.5f;
            vy = -(2.0f + rnd.nextFloat() * 6.0f) * z;
            size = (3.0f + rnd.nextFloat() * 8.0f) * z;
            color = rnd.nextBoolean() ? new Color(0, 240, 255) : new Color(255, 0, 128);
        }

        void update(Random rnd, float speedMultiplier) {
            x += vx * speedMultiplier;
            y += vy * speedMultiplier;
            if (y < -HEIGHT * 0.8f) {
                reset(rnd, false);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Iniciando Motor de Video Procedural (Gemini 4 Argon)...");

        // 1. Sintetizar a Sonoplastia (WAV em disco temporário)
        File audioFile = new File("argon_sfx.wav");
        generateProceduralAudio(audioFile, DURATION_SEC);
        System.out.println("Sonoplastia procedural gerada: " + audioFile.getAbsolutePath());

        // 2. Iniciar pipeline do FFmpeg recebendo bytes brutos (BGR24) + Áudio WAV
        ProcessBuilder pb = new ProcessBuilder(
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", WIDTH + "x" + HEIGHT,
            "-r", String.valueOf(FPS),
            "-i", "-",
            "-i", audioFile.getAbsolutePath(),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "motion_argon.mp4"
        );
        pb.redirectError(ProcessBuilder.Redirect.INHERIT);
        Process ffmpeg = pb.start();

        Random rnd = new Random(42);
        List<Particle> particles = new ArrayList<>();
        for (int i = 0; i < 140; i++) {
            particles.add(new Particle(rnd));
        }

        BufferedImage frame = new BufferedImage(WIDTH, HEIGHT, BufferedImage.TYPE_3BYTE_BGR);
        Graphics2D g = frame.createGraphics();

        // Qualidade Máxima de Renderização
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE);

        try (OutputStream ffmpegIn = new BufferedOutputStream(ffmpeg.getOutputStream(), WIDTH * HEIGHT * 3)) {
            for (int f = 0; f < TOTAL_FRAMES; f++) {
                float time = f / (float) FPS;
                float progress = f / (float) TOTAL_FRAMES;

                renderFrame(g, time, progress, particles, rnd);

                byte[] pixels = ((DataBufferByte) frame.getRaster().getDataBuffer()).getData();
                ffmpegIn.write(pixels);

                if (f % FPS == 0) {
                    System.out.printf("Renderizando: %d%% concluido...%n", (int) (progress * 100));
                }
            }
        }

        g.dispose();
        ffmpeg.waitFor();
        audioFile.delete();
        System.out.println("Video finalizado com sucesso: motion_argon.mp4");
    }

    private static void renderFrame(Graphics2D g, float t, float progress, List<Particle> particles, Random rnd) {
        // Fundo com Motion Trail (leve rastro de movimento)
        g.setColor(new Color(8, 10, 18, 220));
        g.fillRect(0, 0, WIDTH, HEIGHT);

        AffineTransform baseTransform = g.getTransform();

        // Tremor de câmera sutil no impacto inicial (t = 0.5s) e no drop (t = 3.0s)
        float shake = 0f;
        if (t > 0.4f && t < 0.8f) shake = (float) Math.exp(-(t - 0.4f) * 10f) * 28f;
        if (t > 3.0f && t < 3.4f) shake = (float) Math.exp(-(t - 3.0f) * 10f) * 35f;

        float camX = WIDTH / 2f + (float) (Math.sin(t * 45) * shake);
        float camY = HEIGHT / 2f + (float) (Math.cos(t * 38) * shake);
        g.translate(camX, camY);

        // 1. Grade Cibernética Dinâmica ao Fundo
        g.setStroke(new BasicStroke(1.5f));
        g.setColor(new Color(0, 210, 255, 28));
        int gridSpacing = 90;
        float offset = (t * 120) % gridSpacing;
        for (int x = -WIDTH; x <= WIDTH; x += gridSpacing) {
            g.drawLine(x, -HEIGHT, x, HEIGHT);
        }
        for (int y = -HEIGHT; y <= HEIGHT; y += gridSpacing) {
            int drawY = (int) (y + offset);
            g.drawLine(-WIDTH, drawY, WIDTH, drawY);
        }

        // 2. Anéis de Energia e Ondas Senoidais
        float pulse = 1.0f + 0.12f * (float) Math.sin(t * Math.PI * 4);
        int baseRadius = (int) (320 * pulse);

        for (int ring = 0; ring < 3; ring++) {
            float r = baseRadius + ring * 55;
            Path2D wave = new Path2D.Float();
            for (int deg = 0; deg <= 360; deg += 3) {
                double rad = Math.toRadians(deg);
                double distortion = Math.sin(rad * 8 + t * 6 + ring) * 18 * Math.sin(t * 2);
                double px = Math.cos(rad) * (r + distortion);
                double py = Math.sin(rad) * (r + distortion);
                if (deg == 0) wave.moveTo(px, py);
                else wave.lineTo(px, py);
            }
            wave.closePath();

            g.setStroke(new BasicStroke(4f - ring, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
            g.setColor(ring % 2 == 0 ? new Color(0, 240, 255, 160 - ring * 40) : new Color(255, 0, 128, 160 - ring * 40));
            g.draw(wave);
        }

        // 3. Sistema de Partículas com Profundidade (Parallax)
        float speedMult = (t > 3.0f) ? 2.4f : 1.0f;
        for (Particle p : particles) {
            p.update(rnd, speedMult);
            int alpha = Math.min(255, (int) (p.z * 110));
            g.setColor(new Color(p.color.getRed(), p.color.getGreen(), p.color.getBlue(), alpha));
            g.fill(new Ellipse2D.Float(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size));
        }

        // 4. Tipografia Motion Design com Física de Mola (Spring)
        String title = (t < 3.0f) ? "GEMINI 4 ARGON" : "JAVA MOTION 60FPS";
        String subtitle = (t < 3.0f) ? "ENGINE PROCEDURAL" : "100% CODIGO PURO";

        float localT = (t < 3.0f) ? (t - 0.3f) : (t - 3.0f);
        if (localT > 0) {
            float springScale = 1.0f - (float) (Math.exp(-localT * 6.0) * Math.cos(localT * 18.0));
            AffineTransform textTx = g.getTransform();
            g.scale(springScale, springScale);

            Font mainFont = new Font("SansSerif", Font.BOLD, 82);
            g.setFont(mainFont);
            FontMetrics fm = g.getFontMetrics();
            int tw = fm.stringWidth(title);

            // Efeito Glow em Camadas
            for (int glow = 16; glow >= 4; glow -= 4) {
                g.setColor(new Color(0, 240, 255, 35));
                g.drawString(title, -tw / 2, -20 + glow / 4);
            }
            g.setColor(Color.WHITE);
            g.drawString(title, -tw / 2, -20);

            // Subtítulo com Barra de Destaque
            Font subFont = new Font("Monospaced", Font.BOLD, 36);
            g.setFont(subFont);
            FontMetrics sfm = g.getFontMetrics();
            int stw = sfm.stringWidth(subtitle);

            g.setColor(new Color(255, 0, 128, 220));
            g.fillRoundRect(-stw / 2 - 25, 35, stw + 50, 56, 16, 16);

            g.setColor(Color.WHITE);
            g.drawString(subtitle, -stw / 2, 75);

            g.setTransform(textTx);
        }

        g.setTransform(baseTransform);
    }

    // Sintetizador de Áudio Procedural (Impactos Sub-Bass + Pulso Rítmico)
    private static void generateProceduralAudio(File outFile, int durationSeconds) throws IOException {
        float sampleRate = 44100f;
        int totalSamples = (int) (sampleRate * durationSeconds);
        byte[] pcmData = new byte[totalSamples * 2]; // 16-bit mono
        ByteBuffer buffer = ByteBuffer.wrap(pcmData).order(ByteOrder.LITTLE_ENDIAN);

        for (int i = 0; i < totalSamples; i++) {
            double t = i / sampleRate;
            double signal = 0.0;

            // Sub-bass Drop em t = 0.4s e t = 3.0s
            double[] drops = {0.4, 3.0};
            for (double d : drops) {
                if (t >= d && t < d + 1.2) {
                    double dt = t - d;
                    double freq = 140.0 * Math.exp(-dt * 4.5) + 42.0;
                    double env = Math.exp(-dt * 3.0);
                    signal += Math.sin(2 * Math.PI * freq * dt) * env * 0.7;
                }
            }

            // Pulso Sintético Cyberpunk (Arpeggio grave)
            double beat = (t * 4.0) % 1.0;
            double synthFreq = (t < 3.0) ? 110.0 : 146.83;
            double synthEnv = Math.exp(-beat * 6.0) * 0.25;
            signal += Math.tanh(Math.sin(2 * Math.PI * synthFreq * t) * 2.5) * synthEnv;

            // Limiter suave
            signal = Math.max(-0.95, Math.min(0.95, signal));
            short val = (short) (signal * Short.MAX_VALUE);
            buffer.putShort(val);
        }

        AudioFormat format = new AudioFormat(sampleRate, 16, 1, true, false);
        try (ByteArrayInputStream bais = new ByteArrayInputStream(pcmData);
             AudioInputStream ais = new AudioInputStream(bais, format, totalSamples)) {
            AudioSystem.write(ais, AudioFileFormat.Type.WAVE, outFile);
        }
    }
}
