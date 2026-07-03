import os
import scipy.io as sio

def load_data(name):
    data_path = os.path.join("..", "data")
    files = {
        "IP": ("Indian_pines.mat", "indian_pines_corrected", "Indian_pines_gt.mat", "indian_pines_gt"),
        "PU": ("PaviaU.mat", "paviaU", "PaviaU_gt.mat", "paviaU_gt"),
        "SA": ("Salinas.mat", "salinas", "Salinas_gt.mat", "salinas_gt"),
    }
    df, dk, gf, gk = files[name]
    data = sio.loadmat(os.path.join(data_path, df))[dk]
    labels = sio.loadmat(os.path.join(data_path, gf))[gk]
    return data, labels