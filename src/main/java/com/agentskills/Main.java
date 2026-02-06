package com.agentskills;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Main {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String DEFAULT_SYSTEM_PROMPT =
            "你是一个助手。回答要清晰、分步骤，面向 Java 新手。先给出简短计划，再给出最终回答。";

    public static void main(String[] args) throws IOException, InterruptedException {
        String host = System.getenv().getOrDefault("OLLAMA_HOST", "http://localhost:11434");
        String model = System.getenv().getOrDefault("OLLAMA_MODEL", "deepseek-r1:7b");
        Path skillsRoot = Paths.get("skills");

        System.out.println("Agent Skills Learning (Java + Ollama)");
        System.out.println("Host : " + host);
        System.out.println("Model: " + model);
        System.out.println("输入 exit 退出。输入 /help 查看命令。\n");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        SkillRepository repository = new SkillRepository(skillsRoot);
        SkillSession session = new SkillSession();

        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));
        while (true) {
            System.out.print("你> ");
            String user = reader.readLine();
            if (user == null || "exit".equalsIgnoreCase(user.trim())) {
                System.out.println("已退出。");
                break;
            }

            if (user.startsWith("/")) {
                String output = handleCommand(user, repository, session);
                System.out.println(output);
                continue;
            }

            String systemPrompt = buildSystemPrompt(session);
            String reply = chatOnce(client, host, model, systemPrompt, user);
            System.out.println("\nAI> " + reply + "\n");
        }
    }

    private static String handleCommand(String input, SkillRepository repository, SkillSession session) {
        String[] parts = input.trim().split("\\s+", 3);
        String command = parts[0].toLowerCase();

        switch (command) {
            case "/help":
                return """
                        可用命令：
                        /skill list                 列出技能
                        /skill use <name>           启用技能（加载 SKILL.md 正文）
                        /skill clear                清除当前技能
                        /skill show                 查看当前技能状态
                        /skill ref <relative-path>  读取并加载技能资源文件
                        /help                       显示帮助
                        """;
            case "/skill":
                if (parts.length < 2) {
                    return "用法：/skill list | use <name> | clear | show | ref <relative-path>";
                }
                String sub = parts[1].toLowerCase();
                if ("list".equals(sub)) {
                    return repository.listSkills();
                }
                if ("use".equals(sub)) {
                    if (parts.length < 3) {
                        return "用法：/skill use <name>";
                    }
                    Skill skill = repository.getSkill(parts[2]);
                    if (skill == null) {
                        return "未找到技能：" + parts[2];
                    }
                    session.activate(skill);
                    return "已启用技能：" + skill.name;
                }
                if ("clear".equals(sub)) {
                    session.clear();
                    return "已清除当前技能。";
                }
                if ("show".equals(sub)) {
                    return session.describe();
                }
                if ("ref".equals(sub)) {
                    if (parts.length < 3) {
                        return "用法：/skill ref <relative-path>";
                    }
                    return session.loadResource(parts[2]);
                }
                return "未知子命令：" + sub;
            default:
                return "未知命令。输入 /help 查看帮助。";
        }
    }

    private static String buildSystemPrompt(SkillSession session) {
        StringBuilder builder = new StringBuilder(DEFAULT_SYSTEM_PROMPT);
        if (session.activeSkill == null) {
            return builder.toString();
        }

        builder.append("\n\n当前已启用技能：\n");
        builder.append("name: ").append(session.activeSkill.name).append("\n");
        builder.append("description: ").append(session.activeSkill.description).append("\n\n");
        builder.append("SKILL.md 指令：\n").append(session.activeSkill.body).append("\n");

        if (!session.resources.isEmpty()) {
            builder.append("\n已加载资源：\n");
            session.resources.forEach((name, content) -> {
                builder.append("### ").append(name).append("\n");
                builder.append(content).append("\n");
            });
        }

        return builder.toString();
    }

    private static String chatOnce(HttpClient client, String host, String model, String systemPrompt, String userText)
            throws IOException, InterruptedException {
        Map<String, Object> payload = new HashMap<>();
        payload.put("model", model);
        payload.put("stream", false);
        payload.put("messages", new Object[]{
                Map.of("role", "system", "content", systemPrompt),
                Map.of("role", "user", "content", userText)
        });

        String body = MAPPER.writeValueAsString(payload);
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(host + "/api/chat"))
                .timeout(Duration.ofSeconds(60))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() / 100 != 2) {
            return "请求失败: " + response.statusCode() + " " + response.body();
        }

        JsonNode root = MAPPER.readTree(response.body());
        JsonNode message = root.path("message").path("content");
        return message.isMissingNode() ? response.body() : message.asText();
    }

    private static class Skill {
        private final Path dir;
        private final String name;
        private final String description;
        private final String body;

        private Skill(Path dir, String name, String description, String body) {
            this.dir = dir;
            this.name = name;
            this.description = description;
            this.body = body;
        }
    }

    private static class SkillRepository {
        private final Path root;
        private final Map<String, Skill> skills = new LinkedHashMap<>();

        private SkillRepository(Path root) throws IOException {
            this.root = root;
            loadSkills();
        }

        private void loadSkills() throws IOException {
            skills.clear();
            if (!Files.isDirectory(root)) {
                return;
            }
            try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
                for (Path dir : stream) {
                    if (!Files.isDirectory(dir)) {
                        continue;
                    }
                    Path skillFile = dir.resolve("SKILL.md");
                    if (!Files.isRegularFile(skillFile)) {
                        continue;
                    }
                    Skill skill = parseSkillFile(dir, skillFile);
                    skills.put(skill.name, skill);
                }
            }
        }

        private Skill parseSkillFile(Path dir, Path skillFile) throws IOException {
            List<String> lines = Files.readAllLines(skillFile, StandardCharsets.UTF_8);
            Map<String, String> meta = new HashMap<>();
            List<String> bodyLines = new ArrayList<>();

            int index = 0;
            if (!lines.isEmpty() && lines.get(0).trim().equals("---")) {
                index = 1;
                for (; index < lines.size(); index++) {
                    String line = lines.get(index).trim();
                    if (line.equals("---")) {
                        index++;
                        break;
                    }
                    int colon = line.indexOf(':');
                    if (colon > 0) {
                        String key = line.substring(0, colon).trim();
                        String value = line.substring(colon + 1).trim();
                        meta.put(key, value);
                    }
                }
            }
            for (; index < lines.size(); index++) {
                bodyLines.add(lines.get(index));
            }

            String name = meta.getOrDefault("name", dir.getFileName().toString());
            String description = meta.getOrDefault("description", "无描述");
            String body = String.join("\n", bodyLines).trim();
            return new Skill(dir, name, description, body);
        }

        private String listSkills() {
            if (skills.isEmpty()) {
                return "未发现任何技能。请在 skills/ 下添加技能文件夹。";
            }
            StringBuilder builder = new StringBuilder("技能列表：\n");
            skills.values().forEach(skill ->
                    builder.append("- ").append(skill.name).append("：").append(skill.description).append("\n"));
            return builder.toString();
        }

        private Skill getSkill(String name) {
            return skills.get(name);
        }
    }

    private static class SkillSession {
        private Skill activeSkill;
        private final Map<String, String> resources = new LinkedHashMap<>();

        private void activate(Skill skill) {
            this.activeSkill = skill;
            this.resources.clear();
        }

        private void clear() {
            this.activeSkill = null;
            this.resources.clear();
        }

        private String describe() {
            if (activeSkill == null) {
                return "当前没有启用任何技能。";
            }
            StringBuilder builder = new StringBuilder();
            builder.append("当前技能：").append(activeSkill.name).append("\n");
            builder.append("描述：").append(activeSkill.description).append("\n");
            if (resources.isEmpty()) {
                builder.append("资源：未加载\n");
            } else {
                builder.append("资源：\n");
                resources.keySet().forEach(name -> builder.append("- ").append(name).append("\n"));
            }
            return builder.toString();
        }

        private String loadResource(String relativePath) {
            if (activeSkill == null) {
                return "请先 /skill use <name> 启用技能。";
            }
            Path path = activeSkill.dir.resolve(relativePath).normalize();
            if (!path.startsWith(activeSkill.dir)) {
                return "非法路径。";
            }
            if (!Files.isRegularFile(path)) {
                return "未找到资源文件：" + relativePath;
            }
            try {
                String content = Files.readString(path, StandardCharsets.UTF_8);
                resources.put(relativePath, content.trim());
                return "已加载资源：" + relativePath;
            } catch (IOException e) {
                return "读取资源失败：" + e.getMessage();
            }
        }
    }
}
