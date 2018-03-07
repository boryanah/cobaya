# Global
from __future__ import division, print_function
import os
import numpy as np

# Local
from cobaya.likelihoods._cmblikes_prototype import _cmblikes_prototype

# Logger
import logging

# Physical constants
T_CMB = 2.7255  # CMB temperature
h = 6.62606957e-34  # Planck's constant
kB = 1.3806488e-23  # Boltzmann constant
Ghz_Kelvin = h / kB * 1e9


class bicep_keck_2015(_cmblikes_prototype):

    def readIni(self, ini):
        super(self.__class__, self).readIni(ini)
        self.fpivot_dust = ini.float('fpivot_dust', 353.0)
        self.fpivot_sync = ini.float('fpivot_sync', 23.0)
        self.bandpasses = []
        for i, used in enumerate(self.used_map_order):
            self.bandpasses += [
                self.read_bandpass(ini.relativeFileName('bandpass[%s]' % used))]

    def read_bandpass(self, fname):
        bandpass = Bandpass()
        bandpass.R = np.loadtxt(fname)
        nu = bandpass.R[:, 0]
        bandpass.dnu = np.hstack(
            ((nu[1] - nu[0]), (nu[2:] - nu[:-2]) / 2, (nu[-1] - nu[-2])))
        # Calculate thermodynamic temperature conversion between this bandpass
        # and pivot frequencies 353 GHz (usedfor dust) and 150 GHz (used for sync).
        th_int = np.sum(bandpass.dnu * bandpass.R[:, 1] * bandpass.R[:, 0] ** 4 *
                        np.exp(Ghz_Kelvin * bandpass.R[:, 0] / T_CMB) /
                        (np.exp(Ghz_Kelvin * bandpass.R[:, 0] / T_CMB) - 1) ** 2)
        nu0 = self.fpivot_dust
        th0 = (nu0 ** 4 * np.exp(Ghz_Kelvin * nu0 / T_CMB) /
               (np.exp(Ghz_Kelvin * nu0 / T_CMB) - 1) ** 2)
        bandpass.th_dust = th_int / th0
        nu0 = self.fpivot_sync
        th0 = (nu0 ** 4 * np.exp(Ghz_Kelvin * nu0 / T_CMB) /
               (np.exp(Ghz_Kelvin * nu0 / T_CMB) - 1) ** 2)
        bandpass.th_sync = th_int / th0
        return bandpass

    def dust_scaling(self, beta, Tdust, bandpass, nu0):
        """Calculates greybody scaling of dust signal defined at 353 GHz
        to specified bandpass."""
        gb_int = np.sum(bandpass.dnu * bandpass.R[:, 1] * bandpass.R[:, 0] ** (3 + beta) /
                        (np.exp(Ghz_Kelvin * bandpass.R[:, 0] / Tdust) - 1))
        # Calculate values at pivot frequency.
        gb0 = nu0 ** (3 + beta) / (np.exp(Ghz_Kelvin * nu0 / Tdust) - 1)
        # Calculate dust scaling.
        return (gb_int / gb0) / bandpass.th_dust

    def sync_scaling(self, beta, bandpass, nu0):
        """Calculates power-law scaling of synchrotron signal defined at 150 GHz
        to specified bandpass."""
        # Integrate power-law scaling and thermodynamic temperature conversion
        # across experimental bandpass.
        pl_int = np.sum(bandpass.dnu * bandpass.R[:, 1] * bandpass.R[:, 0] ** (2 + beta))
        # Calculate values at pivot frequency.
        pl0 = nu0 ** (2 + beta)
        # Calculate sync scaling.
        return (pl_int / pl0) / bandpass.th_sync

    def add_foregrounds(self, cls, data_params):
        lpivot = 80.0
        Adust = data_params['BBdust']
        Async = data_params['BBsync']
        alphadust = data_params['BBalphadust']
        betadust = data_params['BBbetadust']
        Tdust = data_params['BBTdust']
        alphasync = data_params['BBalphasync']
        betasync = data_params['BBbetasync']
        dustsync_corr = data_params['BBdustsynccorr']
        EEtoBB_dust = data_params['EEtoBB_dust']
        EEtoBB_sync = data_params['EEtoBB_sync']
        fdust = np.empty(self.nmaps_required)
        fsync = np.empty(self.nmaps_required)
        for i in range(self.nmaps_required):
            fdust[i] = self.dust_scaling(
                betadust, Tdust, self.bandpasses[i], self.fpivot_dust)
            fsync[i] = self.sync_scaling(
                betasync, self.bandpasses[i], self.fpivot_sync)
        rat = np.arange(self.pcl_lmin, self.pcl_lmax + 1) / lpivot
        dustpow = Adust * rat ** alphadust
        syncpow = Async * rat ** alphasync
        dustsyncpow = (dustsync_corr * np.sqrt(Adust * Async) *
                       rat ** ((alphadust + alphasync) / 2))
        for i in range(self.nmaps_required):
            for j in range(i + 1):
                CL = cls[i, j]
                dust = fdust[i] * fdust[j]
                sync = fsync[i] * fsync[j]
                dustsync = fdust[i] * fsync[j] + fsync[i] * fdust[j]
                EE = CL.theory_ij[0] == 1 and CL.theory_ij[1] == 1
                if EE:
                    # EE spectrum: multiply foregrounds by EE/BB ratio
                    dust *= EEtoBB_dust
                    sync *= EEtoBB_sync
                    dustsync *= np.sqrt(EEtoBB_sync * EEtoBB_dust)
                if EE or (CL.theory_ij[0] == 2 and CL.theory_ij[1] == 2):
                    # Only add foregrounds to EE or BB.
                    CL.CL += dust * dustpow + sync * syncpow + dustsync * dustsyncpow


class Bandpass(object):
    pass


# Installation routines ##################################################################

def get_path(path):
    return os.path.realpath(os.path.join(path, "data", __name__.split(".")[-1]))


def is_installed(**kwargs):
    if kwargs["data"]:
        if not os.path.exists(os.path.join(get_path(kwargs["path"]), "BK14_cosmomc")):
            return False
    return True


def install(path=None, name=None, force=False, code=False, data=True,
            no_progress_bars=False):
    log = logging.getLogger(__name__)
    # Create common folders: all planck likelihoods share install folder for code and data
    full_path = get_path(path)
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    if not data:
        return True
    log.info("Downloading likelihood data...")
    try:
        from wget import download, bar_thermometer
        wget_kwargs = {"out": full_path,
                       "bar": (bar_thermometer if not no_progress_bars else None)}
        filename = download(r"http://bicepkeck.org/BK14_datarelease/BK14_cosmomc.tgz",
                            **wget_kwargs)
        print("")  # force newline after wget
    except:
        print("")  # force newline after wget
        log.error("Error downloading!")
        return False
    import tarfile
    extension = os.path.splitext(filename)[-1][1:]
    if extension == "tgz":
        extension = "gz"
    tar = tarfile.open(filename, "r:"+extension)
    try:
        tar.extractall(full_path)
        tar.close()
        os.remove(filename)
        log.info("Likelihood data downloaded and uncompressed correctly.")
        return True
    except:
        log.error("Error decompressing downloaded file! Corrupt file?)")
        return False
