import Foundation

enum AgentTools {
    static var definitions: [[String: Any]] {
        [
            tool(
                "read_file",
                "Lê um arquivo texto do repositório em uma branch/ref.",
                [
                    "type": "object",
                    "properties": [
                        "path": ["type": "string", "description": "Caminho no repositório"],
                        "ref": ["type": "string", "description": "Branch/ref; omita para usar a branch base"]
                    ],
                    "required": ["path"]
                ]
            ),
            tool(
                "list_files",
                "Lista arquivos e diretórios em um caminho do repositório.",
                [
                    "type": "object",
                    "properties": [
                        "path": ["type": "string", "description": "Diretório; vazio para raiz"],
                        "ref": ["type": "string", "description": "Branch/ref; omita para usar a branch base"]
                    ]
                ]
            ),
            tool(
                "create_branch",
                "Cria uma branch isolada. O nome precisa começar com agent/.",
                [
                    "type": "object",
                    "properties": [
                        "name": ["type": "string", "description": "Ex.: agent/fix-background-counter"],
                        "from": ["type": "string", "description": "Branch de origem; omita para usar a branch base"]
                    ],
                    "required": ["name"]
                ]
            ),
            tool(
                "write_file",
                "Cria ou substitui um arquivo inteiro em uma branch agent/**.",
                [
                    "type": "object",
                    "properties": [
                        "path": ["type": "string"],
                        "content": ["type": "string"],
                        "branch": ["type": "string"],
                        "message": ["type": "string"]
                    ],
                    "required": ["path", "content", "branch"]
                ]
            ),
            tool(
                "workflow_runs",
                "Consulta os builds recentes do GitHub Actions.",
                [
                    "type": "object",
                    "properties": [
                        "branch": ["type": "string", "description": "Opcional: filtrar por branch"]
                    ]
                ]
            )
        ]
    }

    private static func tool(
        _ name: String,
        _ description: String,
        _ parameters: [String: Any]
    ) -> [String: Any] {
        [
            "type": "function",
            "function": [
                "name": name,
                "description": description,
                "parameters": parameters
            ]
        ]
    }
}
