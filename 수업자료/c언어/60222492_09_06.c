#include <stdio.h>
void main(){
	int i,j;
	for(i=1;i<=10;i=i+3){
		for(j=1;j<=9;j++){
			printf("%d*%d=%d\n",i,j,i*j);
		}
	}
}
