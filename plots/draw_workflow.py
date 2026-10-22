"""Vector drawing primitives; copied into each independent project generator."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)







def workflow(out):
    d=Drawing((0,0,17.6,4.05))
    d.box('contract',1.5,1.9,2.8,1.0,'Contract $K$\nstart $s$, bound $B$',size=8.5)
    for n,x,y,lab in [('oo',5.1,2.85,'$(C_{old},D_{old})$'),('no',8.35,2.85,'$(C_{new},D_{old})$'),
                      ('on',5.1,.95,'$(C_{old},D_{new})$'),('nn',8.35,.95,'$(C_{new},D_{new})$')]:
        d.box(n,x,y,2.65,.8,lab+'\ntrace + verdict',size=8.5)
    d.box('row',11.7,2.85,2.75,.8,'Code effect\nwith data fixed',size=8.5)
    d.box('col',11.7,.95,2.75,.8,'Data effect\nwith code fixed',size=8.5)
    d.box('decision',15.6,1.9,3.55,1.0,'Frontier + certificate\npromotion decision',size=8.5)
    for a,b in [('contract','oo'),('contract','on'),('oo','no'),('on','nn'),('no','row'),('row','decision'),('col','decision')]:
        d.edge(a,b,'e','w')
    for a,b,x in [('oo','on',5.1),('no','nn',8.35)]:
        d.edge(a,b,'s','n',dashed=True);d.edge(b,a,'n','s',dashed=True)
        d.text(x+.18,1.9,'data',size=8,ha='left')
    # Fixed C_new: take the data comparison from the no/nn vertical pair.
    # Route below its label and above nn, then through the inter-column gap.
    d.arrow((8.35,1.9),d.point('col','w'),
            via=[(8.35,1.65),(9.95,1.65),(9.95,.95)])
    for a,b,y in [('oo','no',3.6),('on','nn',.2)]:
        pa=d.point(a,'n' if y>2 else 's');pb=d.point(b,'n' if y>2 else 's')
        d.arrow(pa,pb,True,via=[(pa[0],y),(pb[0],y)])
        d.text((pa[0]+pb[0])/2,y+.02,'code',size=8,va='bottom')
    d.save(out,'workflow')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    out=p.parse_args().output_dir;out.mkdir(parents=True,exist_ok=True);workflow(out)
