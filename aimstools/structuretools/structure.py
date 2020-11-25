from pathlib import Path as Path
import numpy as np
import spglib

import ase.io, ase.spacegroup
from ase.atoms import Atoms, default

from aimstools.misc import *
from aimstools.structuretools.tools import *

from collections import namedtuple
import copy

logger = logging.getLogger("root")


class Structure(Atoms):
    """ Extends the ase.atoms.Atoms class with some specific functions.
    
    Args:
        geometry (str): Path to structure file (.cif, .xyz ..) or atoms object.

    Attributes:
        atoms (Atoms): ASE atoms object.
        sg (spacegroup): Spglib spacegroup object.
        lattice (str): Description of Bravais lattice.
    """

    def __init__(self, geometry=None, **kwargs) -> None:
        if geometry == None:
            atoms = Atoms(**kwargs)
        elif type(geometry) == ase.atoms.Atoms:
            atoms = geometry.copy()
        elif Path(geometry).is_file():
            if str(Path(geometry).parts[-1]) == "geometry.in.next_step":
                atoms = ase.io.read(geometry, format="aims")
            else:
                try:
                    atoms = ase.io.read(geometry)
                except Exception as excpt:
                    logger.error(str(excpt))

        assert type(atoms) == ase.atoms.Atoms, "Atoms not read correctly."
        # Get data from another Atoms object:
        numbers = atoms.get_atomic_numbers()
        positions = atoms.get_positions()
        cell = atoms.get_cell()
        celldisp = atoms.get_celldisp()
        pbc = atoms.get_pbc()
        constraint = [c.copy() for c in atoms.constraints]
        masses = atoms.get_masses()
        magmoms = None
        charges = None
        momenta = None
        if atoms.has("initial_magmoms"):
            magmoms = atoms.get_initial_magnetic_moments()
        if atoms.has("initial_charges"):
            charges = atoms.get_initial_charges()
        if atoms.has("momenta"):
            momenta = atoms.get_momenta()
        self.arrays = {}
        super().__init__(
            numbers=numbers,
            positions=positions,
            cell=cell,
            celldisp=celldisp,
            pbc=pbc,
            constraint=constraint,
            masses=masses,
            magmoms=magmoms,
            charges=charges,
            momenta=momenta,
        )

        try:
            self.sg = ase.spacegroup.get_spacegroup(self, symprec=1e-2)
        except:
            self.sg = ase.spacegroup.Spacegroup(1)
        self.lattice = self.cell.get_bravais_lattice().crystal_family

    def copy(self):
        """Return a copy."""
        atoms = Atoms(
            cell=self.cell, pbc=self.pbc, info=self.info, celldisp=self._celldisp.copy()
        )

        atoms.arrays = {}
        for name, a in self.arrays.items():
            atoms.arrays[name] = a.copy()
        atoms.constraints = copy.deepcopy(self.constraints)
        strc = self.__class__(atoms)
        return strc

    def standardize(self, to_primitive=True, symprec=1e-4) -> None:
        """ Wrapper of the spglib standardize() function with extra features.

        For 2D systems, the non-periodic axis is enforced as the z-axis.
        
        Args:
            to_primitive (bool): If True, primitive cell is obtained. If False, conventional cell is obtained.
            symprec (float): Precision to determine new cell.

        Note:
            The combination of to_primitive=True and a larger value of symprec (1e-2) can be used to refine a structure.
        """

        atoms = self.copy()
        pbc1 = find_nonperiodic_axes(atoms)
        lattice, positions, numbers = (
            atoms.get_cell(),
            atoms.get_scaled_positions(),
            atoms.numbers,
        )
        cell = (lattice, positions, numbers)
        newcell = spglib.standardize_cell(
            cell, to_primitive=to_primitive, no_idealize=False, symprec=symprec
        )
        if newcell == None:
            logger.error("Cell could not be standardized.")
            return None
        else:
            atoms = ase.Atoms(
                scaled_positions=newcell[1],
                numbers=newcell[2],
                cell=newcell[0],
                pbc=atoms.pbc,
            )
            pbc2 = find_nonperiodic_axes(atoms)
            logger.debug("new pbc: {} {} {}".format(*pbc2))
            if pbc1 != pbc2:
                old = [k for k, v in pbc1.items() if v]
                new = [k for k, v in pbc2.items() if v]
                assert len(old) == len(
                    new
                ), "Periodicity changed due to standardization."
                if len(new) == 2:
                    npbcax = list(set([0, 1, 2]) - set(new))[0]
                    atoms = ase.geometry.permute_axes(atoms, new + [npbcax])

            self.__init__(atoms)

    def recenter(self) -> None:
        """ Recenters atoms to be in the unit cell, with vacuum on both sides.

        The unit cell length c is always chosen such that it is larger than a and b.
        
        Returns:
            atoms : modified atoms object.

        Note:
            The ase.atoms.center() method is supposed to do that, but sometimes separates the layers. I didn't find a good way to circumvene that.

         """
        atoms = self.copy()
        atoms.wrap(pretty_translation=True)
        atoms.center(axis=(2))
        mp = atoms.get_center_of_mass(scaled=False)
        cp = (atoms.cell[0] + atoms.cell[1] + atoms.cell[2]) / 2
        pos = atoms.get_positions(wrap=False)
        pos[:, 2] += np.abs((mp - cp))[2]
        for z in range(pos.shape[0]):
            lz = atoms.cell.lengths()[2]
            if pos[z, 2] >= lz:
                pos[z, 2] -= lz
            if pos[z, 2] < 0:
                pos[z, 2] += lz
        atoms.set_positions(pos)
        newcell, newpos, newscal, numbers = (
            atoms.get_cell(),
            atoms.get_positions(wrap=False),
            atoms.get_scaled_positions(wrap=False),
            atoms.numbers,
        )
        z_pos = newpos[:, 2]
        span = np.max(z_pos) - np.min(z_pos)
        newcell[0, 2] = newcell[1, 2] = newcell[2, 0] = newcell[2, 1] = 0.0
        newcell[2, 2] = span + 100.0
        axes = [0, 1, 2]
        lengths = np.linalg.norm(newcell, axis=1)
        order = [x for x, y in sorted(zip(axes, lengths), key=lambda pair: pair[1])]
        while True:
            if (order == [0, 1, 2]) or (order == [1, 0, 2]):
                break
            newcell[2, 2] += 10.0
            lengths = np.linalg.norm(newcell, axis=1)
            order = [x for x, y in sorted(zip(axes, lengths), key=lambda pair: pair[1])]
        newpos = newscal @ newcell
        newpos[:, 2] = z_pos
        atoms = ase.Atoms(
            positions=newpos, numbers=numbers, cell=newcell, pbc=atoms.pbc
        )
        self.__init__(atoms)

    def is_2d(self) -> bool:
        """ Evaluates if structure is qualitatively two-dimensional.

        Note:
            A 2D structure is considered 2D if only one axis is non-periodic.
        
        Returns:
            bool: 2D or not to 2D, that is the question.
        """
        atoms = self.copy()
        pbcax = find_nonperiodic_axes(atoms)
        if sum(list(pbcax.values())) == 2:
            return True
        else:
            return False

    def find_nonperiodic_axes(self) -> dict:
        """ See :func:`~aimstools.structuretools.tools.find_nonperiodic_axes` """
        atoms = self.copy()
        pbc = find_nonperiodic_axes(atoms)
        return pbc

    def find_fragments(self) -> list:
        """ See :func:`~aimstools.structuretools.tools.find_fragments` """
        atoms = self.copy()
        fragments = find_fragments(atoms)
        return fragments

    @property
    def atoms(self):
        """ Returns ase.atoms.Atoms object. """
        atoms = Atoms(
            cell=self.cell, pbc=self.pbc, info=self.info, celldisp=self._celldisp.copy()
        )

        atoms.arrays = {}
        for name, a in self.arrays.items():
            atoms.arrays[name] = a.copy()
        atoms.constraints = copy.deepcopy(self.constraints)
        self._atoms = atoms
        return self._atoms

    def hexagonal_to_rectangular(self):
        """ See :func:`~aimstools.structuretools.tools.hexagonal_to_rectangular` """
        atoms = self.copy()
        atoms = hexagonal_to_rectangular(atoms)
        return self.__class__(atoms)

    def view(self):
        """ Wrapper of ase.visualize.view() function. """
        from ase.visualize import view

        v = view(self.atoms)
        return v