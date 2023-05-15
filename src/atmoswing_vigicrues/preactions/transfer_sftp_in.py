import fnmatch
import os
import tarfile
from pathlib import Path

import paramiko

import atmoswing_vigicrues as asv

from .preaction import PreAction


class TransferSftpIn(PreAction):
    """
    Récupération des prévisions des modèles météo par SFTP.

    Parameters
    ----------
    name: str
        Le nom de l'action
    options: objet
        L'instance contenant les options de l'action. Les champs possibles sont:

        * local_dir : str
            Répertoire cible pour l'enregistrement des fichiers.
        * prefix : str
            Prefix des fichiers à importer.
        * variables : list (optionnel)
            Liste des variables météorologiques à importer.
        * hostname : str
            Adresse du serveur distant.
        * port : int
            Port du serveur distant.
        * username : str
            Utilisateur ayant un accès au serveur.
        * password : str
            Mot de passe de l'utilisateur sur le serveur.
        * proxy_host : str
            Adresse du proxy, si nécessaire.
        * proxy_port : int
            Port du proxy si nécessaire (par défaut: 1080).
        * remote_dir : str
            Chemin sur le serveur distant où se trouvent les fichiers.
        * attempts_max_hours : int
            Décalage temporel autorisé pour rechercher d'anciens fichiers
        * attempts_step_hours : int
            Pas de temps auquel décrémenter la date pour rechercher d'anciens fichiers
    """

    def __init__(self, name, options):
        """
        Initialisation de l'instance TransferSftp
        """
        self.type_name = "Transfert SFTP"
        self.name = name
        self.local_dir = options['local_dir']
        self.prefix = options['prefix']
        self.hostname = options['hostname']
        self.port = int(options['port'])
        self.username = options['username']
        self.password = options['password']
        self.remote_dir = options['remote_dir']

        self._set_attempts_attributes(options)

        if 'variables' in options and len(options['variables']) > 0:
            self.variables = options['variables']
        else:
            self.variables = None

        if 'proxy_host' in options and len(options['proxy_host']) > 0:
            self.proxy_host = options['proxy_host']
            if 'proxy_port' in options and len(options['proxy_port']) > 0:
                self.proxy_port = int(options['proxy_port'])
            else:
                self.proxy_port = 1080
        else:
            self.proxy_host = None

        super().__init__()

    def run(self, date) -> bool:
        """
        Exécution de la récupération par SFTP.

        Parameters
        ----------
        date : datetime.datetime
            Date de la prévision.
        """
        try:

            # Check if files already in the local folder (only with defined variables)
            if self.variables is not None:
                if self._files_already_present(date):
                    print("  -> Fichiers déjà présents localement.")
                    return True

            # Create a transport object for the SFTP connection
            transport = paramiko.Transport((self.hostname, self.port))

            if self.proxy_host:
                transport.start_client()
                transport.open_channel('direct-tcpip',
                                       (self.hostname, self.port),
                                       (self.proxy_host, self.proxy_port))

            # Authenticate with the SFTP server
            transport.connect(username=self.username, password=self.password)

            # Create an SFTP client object
            sftp = transport.open_sftp_client()

            # Change the directory to the desired remote directory
            sftp.chdir(self.remote_dir)

            # Download files
            local_path = Path(self._get_local_path(date))
            forecast_date = date.strftime("%Y%m%d")
            files_count = 0
            for remote_file in sftp.listdir('.'):
                pattern = f'{self.prefix.lower()}*_{forecast_date}*.*'
                if self.variables is not None:
                    for variable in self.variables:
                        pattern = f'{self.prefix.lower()}_{variable.lower()}' \
                                  f'_{forecast_date}*.*'
                        if fnmatch.fnmatch(remote_file.lower(), pattern):
                            break

                if fnmatch.fnmatch(remote_file.lower(), pattern):
                    local_file = local_path / remote_file
                    if local_file.exists():
                        continue
                    sftp.get(remote_file, str(local_file), prefetch=False)
                    self._unpack_if_needed(local_file, local_path)
                    files_count += 1

            # Close the SFTP client and transport objects
            sftp.close()
            transport.close()

            print(f"  -> Nombre de fichiers récupérés : {files_count}.")

        except paramiko.ssh_exception.PasswordRequiredException as e:
            print(f"SFTP PasswordRequiredException {e}")
            return False
        except paramiko.ssh_exception.BadAuthenticationType as e:
            print(f"SFTP BadAuthenticationType {e}")
            return False
        except paramiko.ssh_exception.AuthenticationException as e:
            print(f"SFTP AuthenticationException {e}")
            return False
        except paramiko.ssh_exception.ChannelException as e:
            print(f"SFTP ChannelException {e}")
            return False
        except paramiko.ssh_exception.ProxyCommandFailure as e:
            print(f"SFTP ProxyCommandFailure {e}")
            return False
        except paramiko.ssh_exception.SSHException as e:
            print(f"SFTP SSHException {e}")
            return False
        except FileNotFoundError as e:
            print(f"SFTP FileNotFoundError {e}")
            return False
        except Exception as e:
            print(f"Le rapatriement des données par SFTP a échoué ({e}).")
            return False

        return True

    @staticmethod
    def _chdir_or_mkdir(dir_path, sftp):
        try:
            sftp.chdir(dir_path)
        except OSError:
            sftp.mkdir(dir_path)
            sftp.chdir(dir_path)

    def _get_local_path(self, date):
        local_path = asv.build_date_dir_structure(self.local_dir, date)
        local_path.mkdir(parents=True, exist_ok=True)
        return local_path

    def _files_already_present(self, date):
        local_path = Path(self._get_local_path(date))
        forecast_datetime = date.strftime("%Y%m%d%H")

        for variable in self.variables:
            pattern = f'{self.prefix.lower()}_{variable.lower()}' \
                      f'_{forecast_datetime}*.*'
            local_files = local_path.glob(pattern)
            file_found = False
            for local_file in local_files:
                if fnmatch.fnmatch(str(local_file.name).lower(), pattern):
                    file_found = True
                    break
            if not file_found:
                return False

        return True

    @staticmethod
    def _unpack_if_needed(local_file, local_path):
        if local_file.suffix in ['.gz', '.tgz', '.xz', '.txz', '.bz2',
                                 '.tbz', '.tbz2', '.tb2']:
            file = tarfile.open(local_file)
            for member in file.getmembers():
                if member.isreg():
                    member.name = os.path.basename(member.name)
                    file.extract(member, local_path)
            file.close()
