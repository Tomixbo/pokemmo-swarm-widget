<#
    Lance PokeMMO Swarm Widget automatiquement a l'ouverture de session Windows.

    Cree un raccourci dans le dossier Demarrage de l'utilisateur
    (shell:startup). Rien n'est ecrit dans le registre, et aucun droit
    administrateur n'est requis : le raccourci se supprime a la main depuis ce
    dossier, ou avec -Remove.

    Usage :
        powershell -ExecutionPolicy Bypass -File install_startup.ps1
        powershell -ExecutionPolicy Bypass -File install_startup.ps1 -Remove
        powershell -ExecutionPolicy Bypass -File install_startup.ps1 -Topic mon-topic-prive
#>

param(
    # Vide par defaut : sans topic, le widget suit le flux public d'Alphapedia,
    # ce qui suffit a fonctionner sans aucune configuration. Un topic ntfy
    # personnel n'apporte que les dates d'expiration exactes.
    [string]$Topic = "",
    [string]$Feed = "https://ntfy.pokemmotools.org/alphapings,swarmpings",
    [switch]$Remove
)

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupDir = [Environment]::GetFolderPath('Startup')
$linkPath = Join-Path $startupDir 'PokeMMO Swarm Widget.lnk'

if ($Remove) {
    if (Test-Path $linkPath) {
        Remove-Item $linkPath -Force
        Write-Host "[+] Demarrage automatique desactive." -ForegroundColor Green
    } else {
        Write-Host "[=] Aucun raccourci de demarrage a supprimer."
    }
    exit 0
}

# pythonw.exe et non python.exe : pas de fenetre console au demarrage.
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    Write-Host "[!] pythonw.exe introuvable dans le PATH." -ForegroundColor Red
    Write-Host "    Installe Python ou ajoute-le au PATH, puis relance ce script."
    exit 1
}

$script = Join-Path $projectDir 'swarm_widget.py'
if (-not (Test-Path $script)) {
    Write-Host "[!] swarm_widget.py introuvable dans $projectDir" -ForegroundColor Red
    exit 1
}

$arguments = "`"$script`" --feed $Feed"
if ($Topic) { $arguments += " --topic $Topic" }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = $arguments
# Repertoire de travail : le widget y lit ses sprites et y ecrit sa position.
$shortcut.WorkingDirectory = $projectDir
$shortcut.Description = "PokeMMO Swarm Widget - essaims et alphas PokeMMO"
$shortcut.IconLocation = "$pythonw,0"
$shortcut.Save()

Write-Host "[+] Demarrage automatique active." -ForegroundColor Green
Write-Host "    Raccourci : $linkPath"
Write-Host "    Commande  : $pythonw $arguments"
Write-Host ""
Write-Host "    Le widget retrouvera sa derniere position, son mode d'affichage,"
Write-Host "    son echelle et sa transparence (.widget_state.json)."
Write-Host "    Pour desactiver : install_startup.ps1 -Remove"
